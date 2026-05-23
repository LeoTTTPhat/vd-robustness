#!/usr/bin/env python3
"""Compute calibration-invariant score robustness from paired prediction files."""

from __future__ import annotations

import argparse
import csv
import json
import math
from bisect import bisect_right
from collections import defaultdict
from pathlib import Path


DEFAULT_RUNS = [
    (
        "VulBERTa-public",
        "full CodeXGLUE",
        "results/public_exact/vulberta_mlp_devign/codexglue_full_predictions.jsonl",
    ),
    (
        "LineVul-public",
        "full CodeXGLUE",
        "results/public_exact/linevul_mickymike/codexglue_full_predictions.jsonl",
    ),
    (
        "ReGVD-official-calibrated",
        "full CodeXGLUE",
        "results/public_exact/regvd_codexglue_full_regrun/codexglue_full_scored_predictions.jsonl",
    ),
    (
        "GraphCodeBERT-public",
        "512-origin subset",
        "results/public_exact/graphcodebert_devign/codexglue_512_stratified_predictions.jsonl",
    ),
    (
        "AST-structural-RF-local",
        "512-origin subset",
        "results/public_exact/ast_structural_rf/codexglue_512_stratified_predictions.jsonl",
    ),
    (
        "AST-structural-ExtraTrees-local",
        "full CodeXGLUE",
        "results/public_exact/ast_structural_extra_trees/codexglue_full_predictions.jsonl",
    ),
]


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                row["idx"] = str(row["idx"])
                rows.append(row)
    return rows


def average_ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i + 1
        while j < len(order) and values[order[j]] == values[order[i]]:
            j += 1
        avg = (i + 1 + j) / 2.0
        for k in range(i, j):
            ranks[order[k]] = avg
        i = j
    return ranks


def spearman(x: list[float], y: list[float]) -> float:
    if len(x) < 2:
        return float("nan")
    rx = average_ranks(x)
    ry = average_ranks(y)
    mean_x = sum(rx) / len(rx)
    mean_y = sum(ry) / len(ry)
    num = sum((a - mean_x) * (b - mean_y) for a, b in zip(rx, ry))
    den_x = math.sqrt(sum((a - mean_x) ** 2 for a in rx))
    den_y = math.sqrt(sum((b - mean_y) ** 2 for b in ry))
    if den_x == 0.0 or den_y == 0.0:
        return float("nan")
    rho = num / (den_x * den_y)
    return max(-1.0, min(1.0, rho))


def empirical_cdf_map(clean_scores: list[float]) -> dict[float, float]:
    ranks = average_ranks(clean_scores)
    n = len(clean_scores)
    return {score: rank / n for score, rank in zip(clean_scores, ranks)}


def summarize(detector: str, subset: str, rows: list[dict]) -> list[dict]:
    originals = {row["idx"]: row for row in rows if row["transform"] == "original"}
    clean_scores = [float(row["score"]) for row in originals.values()]
    cdf = empirical_cdf_map(clean_scores)
    ordered_clean_scores = sorted(clean_scores)

    by_transform: dict[str, list[tuple[dict, dict]]] = defaultdict(list)
    for row in rows:
        transform = row["transform"]
        if transform == "original" or row["idx"] not in originals:
            continue
        by_transform[transform].append((originals[row["idx"]], row))

    out: list[dict] = []
    all_pairs: list[tuple[dict, dict]] = []
    for pairs in by_transform.values():
        all_pairs.extend(pairs)

    for transform, pairs in [("ALL", all_pairs), *sorted(by_transform.items())]:
        if not pairs:
            continue
        original_scores = [float(orig["score"]) for orig, _ in pairs]
        variant_scores = [float(var["score"]) for _, var in pairs]
        displacements = [
            abs(
                cdf[float(orig["score"])]
                - cdf.get(float(var["score"]), percentile(ordered_clean_scores, float(var["score"])))
            )
            for orig, var in pairs
        ]
        flip_rate = sum(int(orig["pred"]) != int(var["pred"]) for orig, var in pairs) / len(pairs)
        tifr = sum(displacements) / len(displacements)
        mean_abs_shift = sum(abs(a - b) for a, b in zip(original_scores, variant_scores)) / len(pairs)
        out.append(
            {
                "detector": detector,
                "subset": subset,
                "transform": transform,
                "pairs": len(pairs),
                "decision_flip_rate": flip_rate,
                "tifr": tifr,
                "rank_displacement_robustness": 1.0 - tifr,
                "spearman_score_stability": spearman(original_scores, variant_scores),
                "mean_abs_score_shift": mean_abs_shift,
            }
        )
    return out


def percentile(sorted_reference: list[float], value: float) -> float:
    return bisect_right(sorted_reference, value) / len(sorted_reference)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--output", default="results/calibration_invariant_robustness.csv")
    parser.add_argument("--summary", default="results/calibration_invariant_robustness_summary.json")
    args = parser.parse_args()

    root = Path(args.root)
    all_rows: list[dict] = []
    for detector, subset, rel_path in DEFAULT_RUNS:
        all_rows.extend(summarize(detector, subset, load_jsonl(root / rel_path)))

    fieldnames = [
        "detector",
        "subset",
        "transform",
        "pairs",
        "decision_flip_rate",
        "tifr",
        "rank_displacement_robustness",
        "spearman_score_stability",
        "mean_abs_score_shift",
    ]
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    summary_rows = [row for row in all_rows if row["transform"] == "ALL"]
    summary = root / args.summary
    summary.parent.mkdir(parents=True, exist_ok=True)
    summary.write_text(json.dumps(summary_rows, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
