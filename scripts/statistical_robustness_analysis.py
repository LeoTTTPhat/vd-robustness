#!/usr/bin/env python3
"""Compute imbalance-aware metrics, bootstrap CIs, and paired tests."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
import json
from pathlib import Path
import random

import numpy as np
from scipy.stats import binomtest
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    f1_score,
    matthews_corrcoef,
    precision_score,
    recall_score,
)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def safe_average_precision(y_true: list[int], scores: list[float]) -> float:
    if len(set(y_true)) < 2:
        return 0.0
    return float(average_precision_score(y_true, scores))


def metric_row(rows: list[dict]) -> dict[str, float]:
    y = [int(row["target"]) for row in rows]
    pred = [int(row["pred"]) for row in rows]
    scores = [float(row.get("score", row["pred"])) for row in rows]
    return {
        "n": len(rows),
        "precision": float(precision_score(y, pred, zero_division=0)),
        "recall": float(recall_score(y, pred, zero_division=0)),
        "f1": float(f1_score(y, pred, zero_division=0)),
        "balanced_accuracy": float(balanced_accuracy_score(y, pred)),
        "mcc": float(matthews_corrcoef(y, pred)) if len(set(y)) > 1 else 0.0,
        "pr_auc": safe_average_precision(y, scores),
    }


def percentile_ci(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    return float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))


def bootstrap_metric_delta(
    clean_rows: list[dict],
    variant_rows: list[dict],
    metric_name: str,
    iterations: int,
    seed: int,
) -> tuple[float, float, float]:
    rng = random.Random(seed)
    clean_by_idx = {str(row["idx"]): row for row in clean_rows}
    variant_by_idx = defaultdict(list)
    for row in variant_rows:
        if str(row["idx"]) in clean_by_idx:
            variant_by_idx[str(row["idx"])].append(row)
    idxs = sorted(set(clean_by_idx) & set(variant_by_idx))
    if not idxs:
        return 0.0, 0.0, 0.0

    def score_from_arrays(y: list[int], pred: list[int], scores: list[float]) -> float:
        if metric_name == "f1":
            return float(f1_score(y, pred, zero_division=0))
        if metric_name == "balanced_accuracy":
            return float(balanced_accuracy_score(y, pred))
        if metric_name == "mcc":
            return float(matthews_corrcoef(y, pred)) if len(set(y)) > 1 else 0.0
        if metric_name == "pr_auc":
            return safe_average_precision(y, scores)
        raise ValueError(f"Unsupported metric for bootstrap: {metric_name}")

    clean_units = []
    variant_units = []
    for idx in idxs:
        clean = clean_by_idx[idx]
        clean_units.append(([int(clean["target"])], [int(clean["pred"])], [float(clean.get("score", clean["pred"]))]))
        group = variant_by_idx[idx]
        variant_units.append(
            (
                [int(row["target"]) for row in group],
                [int(row["pred"]) for row in group],
                [float(row.get("score", row["pred"])) for row in group],
            )
        )

    def flatten(units: list[tuple[list[int], list[int], list[float]]], draw: list[int]) -> tuple[list[int], list[int], list[float]]:
        ys: list[int] = []
        preds: list[int] = []
        scores: list[float] = []
        for pos in draw:
            y, pred, score = units[pos]
            ys.extend(y)
            preds.extend(pred)
            scores.extend(score)
        return ys, preds, scores

    positions = list(range(len(idxs)))
    clean_y, clean_pred, clean_score_values = flatten(clean_units, positions)
    variant_y, variant_pred, variant_score_values = flatten(variant_units, positions)
    clean_score = score_from_arrays(clean_y, clean_pred, clean_score_values)
    variant_score = score_from_arrays(variant_y, variant_pred, variant_score_values)
    observed = clean_score - variant_score
    samples = []
    for _ in range(iterations):
        draw = [rng.choice(positions) for _ in positions]
        clean_y, clean_pred, clean_score_values = flatten(clean_units, draw)
        variant_y, variant_pred, variant_score_values = flatten(variant_units, draw)
        samples.append(
            score_from_arrays(clean_y, clean_pred, clean_score_values)
            - score_from_arrays(variant_y, variant_pred, variant_score_values)
        )
    lo, hi = percentile_ci(samples)
    return observed, lo, hi


def flip_ci_and_mcnemar(clean_rows: list[dict], variant_rows: list[dict]) -> dict[str, float]:
    clean_by_idx = {str(row["idx"]): row for row in clean_rows}
    comparable = [row for row in variant_rows if str(row["idx"]) in clean_by_idx]
    n = len(comparable)
    flips = sum(1 for row in comparable if row["pred"] != clean_by_idx[str(row["idx"])]["pred"])
    flip_ci = binomtest(flips, n).proportion_ci(confidence_level=0.95, method="wilson") if n else None

    clean_only_correct = 0
    variant_only_correct = 0
    for row in comparable:
        clean = clean_by_idx[str(row["idx"])]
        clean_correct = int(clean["pred"]) == int(clean["target"])
        variant_correct = int(row["pred"]) == int(row["target"])
        if clean_correct and not variant_correct:
            clean_only_correct += 1
        elif variant_correct and not clean_correct:
            variant_only_correct += 1
    discordant = clean_only_correct + variant_only_correct
    p_value = float(binomtest(min(clean_only_correct, variant_only_correct), discordant, 0.5).pvalue) if discordant else 1.0
    return {
        "flip_count": flips,
        "flip_n": n,
        "flip_rate": flips / n if n else 0.0,
        "flip_ci_low": float(flip_ci.low) if flip_ci else 0.0,
        "flip_ci_high": float(flip_ci.high) if flip_ci else 0.0,
        "mcnemar_clean_only_correct": clean_only_correct,
        "mcnemar_variant_only_correct": variant_only_correct,
        "mcnemar_exact_p": p_value,
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path, default=Path("results/credible_local"))
    parser.add_argument("--iterations", type=int, default=500)
    parser.add_argument("--seed", type=int, default=20260518)
    args = parser.parse_args()

    rows = []
    transform_rows = []
    for dataset_dir in sorted(path for path in args.results_dir.iterdir() if path.is_dir()):
        dataset = dataset_dir.name
        for prediction_path in sorted(dataset_dir.glob("*_predictions.jsonl")):
            detector = prediction_path.name.removesuffix("_predictions.jsonl")
            predictions = read_jsonl(prediction_path)
            clean = [row for row in predictions if row["transform"] == "original"]
            variants = [row for row in predictions if row["transform"] != "original"]
            clean_metrics = metric_row(clean)
            variant_metrics = metric_row(variants)
            flip_stats = flip_ci_and_mcnemar(clean, variants)
            f1_delta, f1_lo, f1_hi = bootstrap_metric_delta(clean, variants, "f1", args.iterations, args.seed)
            bal_delta, bal_lo, bal_hi = bootstrap_metric_delta(
                clean, variants, "balanced_accuracy", args.iterations, args.seed
            )
            rows.append(
                {
                    "dataset": dataset,
                    "detector": detector,
                    "clean_f1": clean_metrics["f1"],
                    "variant_f1": variant_metrics["f1"],
                    "f1_drop": f1_delta,
                    "f1_drop_ci_low": f1_lo,
                    "f1_drop_ci_high": f1_hi,
                    "clean_balanced_accuracy": clean_metrics["balanced_accuracy"],
                    "variant_balanced_accuracy": variant_metrics["balanced_accuracy"],
                    "balanced_accuracy_drop": bal_delta,
                    "balanced_accuracy_drop_ci_low": bal_lo,
                    "balanced_accuracy_drop_ci_high": bal_hi,
                    "clean_mcc": clean_metrics["mcc"],
                    "variant_mcc": variant_metrics["mcc"],
                    "clean_pr_auc": clean_metrics["pr_auc"],
                    "variant_pr_auc": variant_metrics["pr_auc"],
                    **flip_stats,
                }
            )
            for transform in sorted({row["transform"] for row in variants}):
                transform_subset = [row for row in variants if row["transform"] == transform]
                transform_metrics = metric_row(transform_subset)
                transform_rows.append(
                    {
                        "dataset": dataset,
                        "detector": detector,
                        "transform": transform,
                        "f1": transform_metrics["f1"],
                        "balanced_accuracy": transform_metrics["balanced_accuracy"],
                        "mcc": transform_metrics["mcc"],
                        "pr_auc": transform_metrics["pr_auc"],
                        **flip_ci_and_mcnemar(clean, transform_subset),
                    }
                )

    write_csv(args.results_dir / "statistical_robustness_summary.csv", rows)
    write_csv(args.results_dir / "statistical_robustness_by_transform.csv", transform_rows)
    (args.results_dir / "statistical_robustness_summary.json").write_text(
        json.dumps({"overall": rows, "by_transform": transform_rows}, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {len(rows)} overall rows and {len(transform_rows)} transform rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
