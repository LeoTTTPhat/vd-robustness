#!/usr/bin/env python3
"""Summarize executed detector-family robustness predictions."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
import json
from pathlib import Path


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def prf(rows: list[dict]) -> dict[str, float]:
    tp = sum(1 for row in rows if row["pred"] == 1 and row["target"] == 1)
    fp = sum(1 for row in rows if row["pred"] == 1 and row["target"] == 0)
    tn = sum(1 for row in rows if row["pred"] == 0 and row["target"] == 0)
    fn = sum(1 for row in rows if row["pred"] == 0 and row["target"] == 1)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    accuracy = (tp + tn) / len(rows) if rows else 0.0
    return {
        "n": len(rows),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "accuracy": accuracy,
    }


def summarize_prediction_file(dataset: str, detector: str, path: Path) -> tuple[dict, list[dict]]:
    rows = read_jsonl(path)
    originals = {str(row["idx"]): row for row in rows if row["transform"] == "original"}
    variants = [row for row in rows if row["transform"] != "original"]
    clean = prf(list(originals.values()))
    transformed = prf(variants)

    comparable = [row for row in variants if str(row["idx"]) in originals]
    flips = [row for row in comparable if row["pred"] != originals[str(row["idx"])]["pred"]]
    vuln_comparable = [row for row in comparable if row["target"] == 1]
    nonvuln_comparable = [row for row in comparable if row["target"] == 0]
    vuln_flips = [row for row in vuln_comparable if row["pred"] != originals[str(row["idx"])]["pred"]]
    nonvuln_flips = [row for row in nonvuln_comparable if row["pred"] != originals[str(row["idx"])]["pred"]]
    vulnerable_variant_positive = [row for row in vuln_comparable if row["pred"] == 1]

    variants_by_idx: dict[str, list[dict]] = defaultdict(list)
    for row in comparable:
        variants_by_idx[str(row["idx"])].append(row)
    completely_resistant = 0
    for idx, group in variants_by_idx.items():
        original_pred = originals[idx]["pred"]
        if all(row["pred"] == original_pred for row in group):
            completely_resistant += 1

    by_transform = []
    for transform in sorted({row["transform"] for row in variants}):
        transform_rows = [row for row in variants if row["transform"] == transform]
        metrics = prf(transform_rows)
        transform_comparable = [row for row in transform_rows if str(row["idx"]) in originals]
        transform_flips = [row for row in transform_comparable if row["pred"] != originals[str(row["idx"])]["pred"]]
        metrics.update(
            {
                "dataset": dataset,
                "detector": detector,
                "transform": transform,
                "flip_rate": len(transform_flips) / len(transform_comparable) if transform_comparable else 0.0,
            }
        )
        by_transform.append(metrics)

    worst = max(by_transform, key=lambda row: row["flip_rate"]) if by_transform else {"transform": "NA", "flip_rate": 0.0}
    summary = {
        "dataset": dataset,
        "detector": detector,
        "clean_n": clean["n"],
        "variant_n": transformed["n"],
        "clean_precision": clean["precision"],
        "clean_recall": clean["recall"],
        "clean_f1": clean["f1"],
        "clean_accuracy": clean["accuracy"],
        "transformed_f1": transformed["f1"],
        "flip_rate": len(flips) / len(comparable) if comparable else 0.0,
        "vulnerable_flip_rate": len(vuln_flips) / len(vuln_comparable) if vuln_comparable else 0.0,
        "nonvulnerable_flip_rate": len(nonvuln_flips) / len(nonvuln_comparable) if nonvuln_comparable else 0.0,
        "vulnerable_variant_recall": len(vulnerable_variant_positive) / len(vuln_comparable) if vuln_comparable else 0.0,
        "complete_resistance": completely_resistant / len(variants_by_idx) if variants_by_idx else 0.0,
        "worst_transform": worst["transform"],
        "worst_transform_flip_rate": worst["flip_rate"],
        "prediction_file": str(path),
    }
    return summary, by_transform


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path, default=Path("results/credible_local"))
    args = parser.parse_args()

    summary_rows = []
    transform_rows = []
    for dataset_dir in sorted(path for path in args.results_dir.iterdir() if path.is_dir()):
        dataset = dataset_dir.name
        for prediction_path in sorted(dataset_dir.glob("*_predictions.jsonl")):
            detector = prediction_path.name.removesuffix("_predictions.jsonl")
            summary, by_transform = summarize_prediction_file(dataset, detector, prediction_path)
            summary_rows.append(summary)
            transform_rows.extend(by_transform)

    write_csv(args.results_dir / "credible_local_summary.csv", summary_rows)
    write_csv(args.results_dir / "credible_local_by_transform.csv", transform_rows)
    (args.results_dir / "credible_local_summary.json").write_text(
        json.dumps({"overall": summary_rows, "by_transform": transform_rows}, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {len(summary_rows)} detector-dataset summaries and {len(transform_rows)} transform summaries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
