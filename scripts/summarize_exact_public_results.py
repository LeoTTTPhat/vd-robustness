#!/usr/bin/env python3
"""Summarize exact public detector predictions for robustness reporting."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from statistics import NormalDist

try:
    from sklearn.metrics import (
        average_precision_score,
        balanced_accuracy_score,
        f1_score,
        matthews_corrcoef,
        precision_score,
        recall_score,
    )
except Exception as exc:  # pragma: no cover - optional dependency guard.
    raise SystemExit("Install scikit-learn to summarize detector outputs.") from exc


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def read_regvd_predictions(predictions: Path, metadata: Path) -> list[dict]:
    meta = {row["idx"]: row for row in read_jsonl(metadata)}
    rows = []
    with predictions.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            variant_id, pred = line.rstrip("\n").split("\t")
            source = meta[variant_id]
            rows.append(
                {
                    "idx": source.get("source_idx", variant_id.split("__", 1)[0]),
                    "variant_id": variant_id,
                    "transform": source.get("transform", "original"),
                    "target": int(source["target"]),
                    "pred": int(pred),
                    "score": float(pred),
                }
            )
    return rows


def wilson_ci(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    z = NormalDist().inv_cdf(1 - alpha / 2)
    phat = k / n
    denom = 1 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    margin = z * math.sqrt((phat * (1 - phat) + z * z / (4 * n)) / n) / denom
    return max(0.0, center - margin), min(1.0, center + margin)


def metrics(rows: list[dict]) -> dict[str, float]:
    y = [int(r["target"]) for r in rows]
    pred = [int(r["pred"]) for r in rows]
    score = [float(r.get("score", r["pred"])) for r in rows]
    return {
        "precision": precision_score(y, pred, zero_division=0),
        "recall": recall_score(y, pred, zero_division=0),
        "f1": f1_score(y, pred, zero_division=0),
        "balanced_accuracy": balanced_accuracy_score(y, pred),
        "mcc": matthews_corrcoef(y, pred),
        "pr_auc": average_precision_score(y, score) if len(set(y)) > 1 else float("nan"),
    }


def summarize_rows(dataset: str, detector: str, rows: list[dict], prediction_file: Path) -> tuple[dict, list[dict]]:
    originals = [r for r in rows if r.get("transform") == "original"]
    variants = [r for r in rows if r.get("transform") != "original"]
    original_by_idx = {str(r["idx"]): r for r in originals}
    paired = [r for r in variants if str(r["idx"]) in original_by_idx]
    flip_count = sum(int(r["pred"]) != int(original_by_idx[str(r["idx"])]["pred"]) for r in paired)
    lo, hi = wilson_ci(flip_count, len(paired))
    clean_metrics = metrics(originals)
    variant_metrics = metrics(variants)
    summary = {
        "dataset": dataset,
        "detector": detector,
        "clean_n": len(originals),
        **{f"clean_{k}": v for k, v in clean_metrics.items()},
        "variant_n": len(variants),
        **{f"variant_{k}": v for k, v in variant_metrics.items()},
        "flip_rate": flip_count / len(paired) if paired else float("nan"),
        "flip_ci_low": lo,
        "flip_ci_high": hi,
        "flip_count": flip_count,
        "flip_n": len(paired),
        "prediction_file": str(prediction_file),
    }
    by_transform = []
    for transform in sorted({r["transform"] for r in variants}):
        group = [r for r in variants if r["transform"] == transform]
        paired_group = [r for r in group if str(r["idx"]) in original_by_idx]
        group_flips = sum(int(r["pred"]) != int(original_by_idx[str(r["idx"])]["pred"]) for r in paired_group)
        group_lo, group_hi = wilson_ci(group_flips, len(paired_group))
        row = {
            "dataset": dataset,
            "detector": detector,
            "transform": transform,
            "n": len(group),
            **metrics(group),
            "flip_rate": group_flips / len(paired_group) if paired_group else float("nan"),
            "flip_ci_low": group_lo,
            "flip_ci_high": group_hi,
            "flip_count": group_flips,
            "flip_n": len(paired_group),
        }
        by_transform.append(row)
    return summary, by_transform


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--hf", action="append", default=[], help="detector=prediction_jsonl")
    parser.add_argument("--regvd", help="detector=predictions_txt:metadata_jsonl")
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--by-transform", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    args = parser.parse_args()

    summaries: list[dict] = []
    transform_rows: list[dict] = []
    for item in args.hf:
        detector, path = item.split("=", 1)
        summary, by_transform = summarize_rows(args.dataset, detector, read_jsonl(Path(path)), Path(path))
        summaries.append(summary)
        transform_rows.extend(by_transform)
    if args.regvd:
        detector, rest = args.regvd.split("=", 1)
        pred_path, meta_path = rest.split(":", 1)
        rows = read_regvd_predictions(Path(pred_path), Path(meta_path))
        summary, by_transform = summarize_rows(args.dataset, detector, rows, Path(pred_path))
        summaries.append(summary)
        transform_rows.extend(by_transform)

    write_csv(args.summary, summaries)
    write_csv(args.by_transform, transform_rows)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps({"summary": summaries, "by_transform": transform_rows}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"summary": str(args.summary), "by_transform": str(args.by_transform), "detectors": len(summaries)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
