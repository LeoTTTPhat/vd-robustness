#!/usr/bin/env python3
"""Analyze robustness, simple paired statistics, and aggregation mitigation."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import random


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def safe_div(num: float, den: float) -> float:
    return num / den if den else 0.0


def metrics(rows: list[dict]) -> dict:
    tp = sum(1 for r in rows if r["target"] == 1 and r["pred"] == 1)
    fp = sum(1 for r in rows if r["target"] == 0 and r["pred"] == 1)
    tn = sum(1 for r in rows if r["target"] == 0 and r["pred"] == 0)
    fn = sum(1 for r in rows if r["target"] == 1 and r["pred"] == 0)
    precision = safe_div(tp, tp + fp)
    recall = safe_div(tp, tp + fn)
    f1 = safe_div(2 * precision * recall, precision + recall)
    return {
        "n": len(rows),
        "accuracy": safe_div(tp + tn, len(rows)),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
    }


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    k = (len(values) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(values) - 1)
    frac = k - lo
    return values[lo] * (1 - frac) + values[hi] * frac


def bootstrap_drop(original: list[dict], transformed: list[dict], metric: str, seed: int = 20260517, n: int = 500) -> dict:
    rng = random.Random(seed)
    paired = list(zip(original, transformed))
    drops = []
    for _ in range(n):
        sample = [paired[rng.randrange(len(paired))] for _ in paired]
        clean_rows = [a for a, _ in sample]
        trans_rows = [b for _, b in sample]
        drops.append(metrics(clean_rows)[metric] - metrics(trans_rows)[metric])
    return {
        "mean": sum(drops) / len(drops),
        "ci95_low": percentile(drops, 0.025),
        "ci95_high": percentile(drops, 0.975),
    }


def mcnemar(original: list[dict], transformed: list[dict]) -> dict:
    b = c = 0
    for a, t in zip(original, transformed):
        a_correct = a["pred"] == a["target"]
        t_correct = t["pred"] == t["target"]
        if a_correct and not t_correct:
            b += 1
        elif (not a_correct) and t_correct:
            c += 1
    stat = ((abs(b - c) - 1) ** 2 / (b + c)) if (b + c) else 0.0
    return {"b_clean_only_correct": b, "c_transformed_only_correct": c, "mcnemar_chi2_cc": stat}


def analyze_file(path: Path, model_name: str) -> dict:
    rows = read_jsonl(path)
    by_transform: dict[str, list[dict]] = defaultdict(list)
    by_idx: dict[str, dict[str, dict]] = defaultdict(dict)
    for row in rows:
        by_transform[row["transform"]].append(row)
        by_idx[str(row["idx"])][row["transform"]] = row

    clean = by_transform["original"]
    clean_by_idx = {str(r["idx"]): r for r in clean}
    clean_metrics = metrics(clean)
    transform_metrics = {t: metrics(rs) for t, rs in sorted(by_transform.items())}

    sensitivity = {}
    flip_total = flip_vuln = flip_nonvuln = vuln_total = nonvuln_total = 0
    robust_correct = clean_correct = 0
    robust_vuln_all = 0
    total_vuln = 0
    clean_detected_vuln = 0
    complete_resistant = 0

    for idx, variants in by_idx.items():
        original = variants["original"]
        transformed = [v for t, v in variants.items() if t != "original"]
        if original["pred"] == original["target"]:
            clean_correct += 1
            if all(v["pred"] == v["target"] for v in transformed):
                robust_correct += 1
        if original["target"] == 1:
            total_vuln += 1
            if original["pred"] == 1 and all(v["pred"] == 1 for v in transformed):
                robust_vuln_all += 1
            if original["pred"] == 1:
                clean_detected_vuln += 1
                if all(v["pred"] == 1 for v in transformed):
                    complete_resistant += 1
        for v in transformed:
            if original["target"] == 1:
                vuln_total += 1
            else:
                nonvuln_total += 1
            if v["pred"] != original["pred"]:
                flip_total += 1
                if original["target"] == 1:
                    flip_vuln += 1
                else:
                    flip_nonvuln += 1

    for transform, transformed_rows in sorted(by_transform.items()):
        if transform == "original":
            continue
        paired_original = [clean_by_idx[str(r["idx"])] for r in transformed_rows]
        flip = sum(1 for o, t in zip(paired_original, transformed_rows) if o["pred"] != t["pred"])
        vuln_rows = [(o, t) for o, t in zip(paired_original, transformed_rows) if o["target"] == 1]
        non_rows = [(o, t) for o, t in zip(paired_original, transformed_rows) if o["target"] == 0]
        tp_to_fn = sum(1 for o, t in vuln_rows if o["pred"] == 1 and t["pred"] == 0)
        tn_to_fp = sum(1 for o, t in non_rows if o["pred"] == 0 and t["pred"] == 1)
        sensitivity[transform] = {
            "n": len(transformed_rows),
            "flip_rate": safe_div(flip, len(transformed_rows)),
            "vulnerable_flip_rate": safe_div(sum(1 for o, t in vuln_rows if o["pred"] != t["pred"]), len(vuln_rows)),
            "non_vulnerable_flip_rate": safe_div(sum(1 for o, t in non_rows if o["pred"] != t["pred"]), len(non_rows)),
            "tp_to_fn_rate": safe_div(tp_to_fn, len(vuln_rows)),
            "tn_to_fp_rate": safe_div(tn_to_fp, len(non_rows)),
            "f1_drop": clean_metrics["f1"] - transform_metrics[transform]["f1"],
            "recall_drop": clean_metrics["recall"] - transform_metrics[transform]["recall"],
            "f1_drop_bootstrap": bootstrap_drop(paired_original, transformed_rows, "f1"),
            "recall_drop_bootstrap": bootstrap_drop(paired_original, transformed_rows, "recall"),
            "mcnemar": mcnemar(paired_original, transformed_rows),
        }

    aggregation = []
    for strategy in ("original_only", "majority_vote", "mean_score", "max_risk"):
        agg_rows = []
        for idx, variants in by_idx.items():
            original = variants["original"]
            all_rows = list(variants.values())
            if strategy == "original_only":
                pred = original["pred"]
                score = original["score"]
            elif strategy == "majority_vote":
                pred = int(sum(r["pred"] for r in all_rows) >= (len(all_rows) / 2))
                score = sum(r["pred"] for r in all_rows) / len(all_rows)
            elif strategy == "mean_score":
                score = sum(r["score"] for r in all_rows) / len(all_rows)
                pred = int(score >= 0)
            else:
                pred = int(any(r["pred"] == 1 for r in all_rows))
                score = max(r["score"] for r in all_rows)
            agg_rows.append({"target": original["target"], "pred": pred, "score": score})
        m = metrics(agg_rows)
        m["strategy"] = strategy
        aggregation.append(m)

    return {
        "model": model_name,
        "prediction_file": str(path),
        "clean": clean_metrics,
        "by_transform": transform_metrics,
        "overall_robustness": {
            "prediction_flip_rate": safe_div(flip_total, vuln_total + nonvuln_total),
            "vulnerable_flip_rate": safe_div(flip_vuln, vuln_total),
            "non_vulnerable_flip_rate": safe_div(flip_nonvuln, nonvuln_total),
            "robust_accuracy": safe_div(robust_correct, clean_correct),
            "robust_recall": safe_div(robust_vuln_all, total_vuln),
            "complete_resistance": safe_div(complete_resistant, clean_detected_vuln),
        },
        "sensitivity": sensitivity,
        "aggregation": aggregation,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", nargs="+", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    analyses = []
    for path in args.predictions:
        model_name = path.name.replace("_predictions.jsonl", "")
        analyses.append(analyze_file(path, model_name))

    result = {"models": analyses}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

