#!/usr/bin/env python3
"""Compute richer aggregation and mechanism analyses for exact public runs."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import expit, logit
from scipy.stats import norm
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, f1_score, matthews_corrcoef, precision_score, recall_score
from sklearn.preprocessing import OneHotEncoder, StandardScaler


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def metrics(labels: np.ndarray, preds: np.ndarray) -> dict[str, float]:
    return {
        "precision": precision_score(labels, preds, zero_division=0),
        "recall": recall_score(labels, preds, zero_division=0),
        "f1": f1_score(labels, preds, zero_division=0),
        "balanced_accuracy": balanced_accuracy_score(labels, preds),
        "mcc": matthews_corrcoef(labels, preds),
    }


def tune_f1_threshold(scores: np.ndarray, labels: np.ndarray) -> tuple[float, float]:
    candidates = np.unique(np.concatenate([np.quantile(scores, np.linspace(0.001, 0.999, 300)), np.array([0.5])]))
    best_t = float(candidates[0])
    best = -1.0
    for threshold in candidates:
        value = f1_score(labels, (scores >= threshold).astype(int), zero_division=0)
        if value > best:
            best = float(value)
            best_t = float(threshold)
    return best_t, best


def summarize_aggregation(detector: str, rows: list[dict]) -> list[dict]:
    df = pd.DataFrame(rows)
    df["idx"] = df["idx"].astype(str)
    original = df[df["transform"] == "original"].copy()
    labels = original.set_index("idx")["target"].astype(int)
    clean_scores = original.set_index("idx")["score"].astype(float)
    clean_threshold, _ = tune_f1_threshold(clean_scores.to_numpy(), labels.to_numpy())

    grouped = df.groupby("idx", sort=True)
    out: list[dict] = []
    strategies: list[tuple[str, pd.Series, float]] = []
    strategies.append(("original_fixed_0.5", clean_scores, 0.5))
    strategies.append(("original_clean_f1_calibrated", clean_scores, clean_threshold))
    strategies.append(("max_risk_fixed_0.5", grouped["score"].max(), 0.5))
    strategies.append(("mean_probability_fixed_0.5", grouped["score"].mean(), 0.5))
    mean_probability = grouped["score"].mean()
    mean_t, _ = tune_f1_threshold(mean_probability.loc[labels.index].to_numpy(), labels.to_numpy())
    strategies.append(("mean_probability_clean_f1_calibrated", mean_probability, mean_t))
    mean_logit = grouped["score"].apply(lambda s: float(expit(np.mean(logit(np.clip(s.astype(float), 1e-6, 1 - 1e-6))))))
    logit_t, _ = tune_f1_threshold(mean_logit.loc[labels.index].to_numpy(), labels.to_numpy())
    strategies.append(("mean_logit_clean_f1_calibrated", mean_logit, logit_t))

    pred_matrix = grouped["pred"].apply(lambda s: list(map(int, s))).reindex(labels.index)
    majority_score = pred_matrix.apply(lambda values: sum(values) / len(values))
    strategies.append(("majority_vote", majority_score, 0.5))

    for strategy, scores, threshold in strategies:
        aligned_scores = scores.reindex(labels.index).astype(float)
        preds = (aligned_scores.to_numpy() >= threshold).astype(int)
        row = {
            "detector": detector,
            "strategy": strategy,
            "threshold": threshold,
            "coverage": 1.0,
            "n": int(len(labels)),
            **metrics(labels.to_numpy(), preds),
        }
        out.append(row)

    disagreements = pred_matrix.apply(lambda values: len(set(values)) > 1)
    retained = labels.index[~disagreements.reindex(labels.index).fillna(False).to_numpy()]
    if len(retained):
        retained_scores = clean_scores.reindex(retained).astype(float)
        retained_labels = labels.reindex(retained).astype(int)
        preds = (retained_scores.to_numpy() >= 0.5).astype(int)
        out.append(
            {
                "detector": detector,
                "strategy": "selective_abstain_on_disagreement",
                "threshold": 0.5,
                "coverage": len(retained) / len(labels),
                "n": int(len(retained)),
                **metrics(retained_labels.to_numpy(), preds),
            }
        )
    return out


def summarize_logistic(detector: str, rows: list[dict], transformed_rows: dict[str, dict]) -> list[dict]:
    df = pd.DataFrame(rows)
    df["idx"] = df["idx"].astype(str)
    originals = df[df["transform"] == "original"].set_index("idx")
    variants = df[df["transform"] != "original"].copy()
    variants["original_pred"] = variants["idx"].map(originals["pred"].astype(int))
    variants["original_score"] = variants["idx"].map(originals["score"].astype(float))
    variants["flip"] = (variants["pred"].astype(int) != variants["original_pred"].astype(int)).astype(int)
    variants["score_margin"] = (variants["original_score"].astype(float) - 0.5).abs()
    variants["label"] = variants["target"].astype(int)
    variants["code_len"] = variants["variant_id"].map(lambda vid: len(transformed_rows.get(str(vid), {}).get("func", "")))
    variants["token_len_proxy"] = variants["variant_id"].map(lambda vid: len(transformed_rows.get(str(vid), {}).get("func", "").split()))
    variants["truncation_proxy"] = (variants["token_len_proxy"] > 512).astype(int)

    cat = variants[["transform"]]
    encoder = OneHotEncoder(drop="first", sparse_output=False)
    x_cat = encoder.fit_transform(cat)
    numeric = variants[["label", "score_margin", "code_len", "token_len_proxy", "truncation_proxy"]].astype(float).to_numpy()
    scaler = StandardScaler()
    x_num = scaler.fit_transform(numeric)
    x = np.hstack([x_cat, x_num])
    y = variants["flip"].to_numpy()
    if len(set(y)) < 2:
        return []

    model = LogisticRegression(max_iter=2000, class_weight="balanced", solver="lbfgs")
    model.fit(x, y)
    names = list(encoder.get_feature_names_out(["transform"])) + ["label_vulnerable", "score_margin", "code_len", "token_len_proxy", "truncation_proxy"]
    coefs = model.coef_[0]
    probs = model.predict_proba(x)[:, 1]
    # Approximate Wald intervals from observed Fisher information.
    w = probs * (1 - probs)
    fisher = x.T @ (x * w[:, None]) + np.eye(x.shape[1]) * 1e-6
    cov = np.linalg.pinv(fisher)
    se = np.sqrt(np.diag(cov))
    rows_out: list[dict] = []
    for name, coef, se_value in zip(names, coefs, se):
        z = coef / se_value if se_value else float("nan")
        p = 2 * (1 - norm.cdf(abs(z))) if math.isfinite(z) else float("nan")
        rows_out.append(
            {
                "detector": detector,
                "feature": name,
                "coef_log_odds": float(coef),
                "odds_ratio": float(math.exp(coef)) if abs(coef) < 50 else float("inf"),
                "ci_low_or": float(math.exp(coef - 1.96 * se_value)) if abs(coef) < 50 else float("nan"),
                "ci_high_or": float(math.exp(coef + 1.96 * se_value)) if abs(coef) < 50 else float("nan"),
                "p_value": float(p),
            }
        )
    return rows_out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vulberta", type=Path, default=Path("results/public_exact/vulberta_mlp_devign/codexglue_full_predictions.jsonl"))
    parser.add_argument("--linevul", type=Path, default=Path("results/public_exact/linevul_mickymike/codexglue_full_predictions.jsonl"))
    parser.add_argument("--transformed", type=Path, default=Path("data/processed/codexglue_test_expanded_transformed.jsonl"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/public_exact"))
    args = parser.parse_args()

    transformed_rows = {row["variant_id"]: row for row in read_jsonl(args.transformed)}
    detectors = {
        "VulBERTa-public": read_jsonl(args.vulberta),
        "LineVul-public": read_jsonl(args.linevul),
    }
    aggregation_rows: list[dict] = []
    logistic_rows: list[dict] = []
    for detector, rows in detectors.items():
        aggregation_rows.extend(summarize_aggregation(detector, rows))
        logistic_rows.extend(summarize_logistic(detector, rows, transformed_rows))

    write_csv(args.output_dir / "exact_public_enhanced_aggregation.csv", aggregation_rows)
    write_csv(args.output_dir / "exact_public_flip_logistic_regression.csv", logistic_rows)
    (args.output_dir / "exact_public_enhanced_analysis.json").write_text(
        json.dumps({"aggregation": aggregation_rows, "logistic": logistic_rows}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"aggregation_rows": len(aggregation_rows), "logistic_rows": len(logistic_rows)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
