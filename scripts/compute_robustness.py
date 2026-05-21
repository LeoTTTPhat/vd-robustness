#!/usr/bin/env python3
"""Compute robustness metrics from detector predictions.

Expected JSONL fields:
  idx, variant_id, transform, target, pred

Optional:
  score
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def safe_div(num: float, den: float) -> float:
    return num / den if den else 0.0


def classification_metrics(rows: list[dict]) -> dict:
    tp = sum(1 for r in rows if r["target"] == 1 and r["pred"] == 1)
    fp = sum(1 for r in rows if r["target"] == 0 and r["pred"] == 1)
    tn = sum(1 for r in rows if r["target"] == 0 and r["pred"] == 0)
    fn = sum(1 for r in rows if r["target"] == 1 and r["pred"] == 0)
    precision = safe_div(tp, tp + fp)
    recall = safe_div(tp, tp + fn)
    return {
        "n": len(rows),
        "accuracy": safe_div(tp + tn, len(rows)),
        "precision": precision,
        "recall": recall,
        "f1": safe_div(2 * precision * recall, precision + recall),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    rows = list(read_jsonl(args.predictions))
    for row in rows:
        for field in ("idx", "transform", "target", "pred"):
            if field not in row:
                raise ValueError(f"Missing required field {field!r}: {row}")

    by_transform: dict[str, list[dict]] = defaultdict(list)
    by_idx: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_transform[row["transform"]].append(row)
        by_idx[str(row["idx"])].append(row)

    clean = by_transform.get("original", [])
    clean_by_idx = {str(r["idx"]): r for r in clean}

    flip_count = 0
    transformed_count = 0
    robust_correct = 0
    clean_correct = 0
    complete_resistant_vuln = 0
    clean_detected_vuln = 0

    for idx, variants in by_idx.items():
        original = clean_by_idx.get(idx)
        if not original:
            continue
        transformed = [v for v in variants if v["transform"] != "original"]
        if original["pred"] == original["target"]:
            clean_correct += 1
            if all(v["pred"] == v["target"] for v in transformed):
                robust_correct += 1
        if original["target"] == 1 and original["pred"] == 1:
            clean_detected_vuln += 1
            if all(v["pred"] == 1 for v in transformed):
                complete_resistant_vuln += 1
        for variant in transformed:
            transformed_count += 1
            if variant["pred"] != original["pred"]:
                flip_count += 1

    metrics_by_transform = {
        transform: classification_metrics(transform_rows)
        for transform, transform_rows in sorted(by_transform.items())
    }

    summary = {
        "overall": {
            "samples_with_original": len(clean_by_idx),
            "prediction_flip_rate": safe_div(flip_count, transformed_count),
            "robust_accuracy": safe_div(robust_correct, clean_correct),
            "complete_resistance": safe_div(complete_resistant_vuln, clean_detected_vuln),
        },
        "by_transform": metrics_by_transform,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary["overall"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

