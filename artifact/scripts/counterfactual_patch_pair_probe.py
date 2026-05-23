#!/usr/bin/env python3
"""Analyze vulnerability counterfactual patch-pair ordering on Big-Vul pairs."""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
from collections import defaultdict
from pathlib import Path


DEFAULT_PREDICTIONS = [
    ("VulBERTa-public", "results/public_exact/vulberta_mlp_devign/bigvul_patch_pairs_predictions.jsonl"),
    ("LineVul-public", "results/public_exact/linevul_mickymike/bigvul_patch_pairs_predictions.jsonl"),
    (
        "ReGVD-official-validation-calibrated",
        "results/public_exact/regvd_codexglue_full_regrun/bigvul_patch_pairs_scored_predictions.jsonl",
    ),
    ("CodeBERT-Devign-local", "results/credible_local/bigvul/codebert_devign_local_predictions.jsonl"),
    ("VulBERTa-local", "results/credible_local/bigvul/vulberta_devign_local_predictions.jsonl"),
    ("LineVul-local", "results/credible_local/bigvul/linevul_local_predictions.jsonl"),
    ("ReGVD-structural-local", "results/credible_local/bigvul/regvd_structural_local_predictions.jsonl"),
]


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]


def base_id(idx: str) -> str:
    return re.sub(r"-(before|after)$", "", idx)


def side(idx: str) -> str | None:
    suffix = idx.rsplit("-", 1)[-1]
    return suffix if suffix in {"before", "after"} else None


def percentile(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    frac = pos - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac


def bootstrap_ci(pairs: list[dict], key: str, rounds: int = 2000) -> tuple[float, float]:
    rng = random.Random(20260523)
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in pairs:
        grouped[row["base_id"]].append(row)
    groups = list(grouped.values())
    stats: list[float] = []
    for _ in range(rounds):
        sample = [row for _ in groups for row in rng.choice(groups)]
        stats.append(sum(row[key] for row in sample) / len(sample))
    return percentile(stats, 0.025), percentile(stats, 0.975)


def summarize_rows(detector: str, rows: list[dict], metadata: dict[str, dict]) -> list[dict]:
    by_pair: dict[tuple[str, str], dict[str, dict]] = defaultdict(dict)
    for row in rows:
        row_side = side(str(row["idx"]))
        if row_side is None:
            continue
        by_pair[(base_id(str(row["idx"])), row["transform"])][row_side] = row

    pairs: list[dict] = []
    for (base, transform), both in sorted(by_pair.items()):
        if "before" not in both or "after" not in both:
            continue
        before = both["before"]
        after = both["after"]
        cwe = metadata.get(before["idx"], metadata.get(after["idx"], {})).get("cwe", "unknown")
        score_margin = float(before["score"]) - float(after["score"])
        pred_margin = int(before["pred"]) - int(after["pred"])
        pairs.append(
            {
                "detector": detector,
                "base_id": base,
                "transform": transform,
                "cwe": cwe or "unknown",
                "score_margin": score_margin,
                "vdcp_success": 1.0 if score_margin > 0 else 0.0,
                "score_tie": 1.0 if score_margin == 0 else 0.0,
                "decision_success": 1.0 if pred_margin > 0 else 0.0,
            }
        )
    return pairs


def aggregate(detector: str, rows: list[dict], transform: str) -> dict:
    subset = rows if transform == "ALL" else [row for row in rows if row["transform"] == transform]
    n = len(subset)
    if n == 0:
        return {
            "detector": detector,
            "transform": transform,
            "pairs": 0,
            "vdcp": float("nan"),
            "vdcp_ci_low": float("nan"),
            "vdcp_ci_high": float("nan"),
            "mean_score_margin": float("nan"),
            "score_tie_rate": float("nan"),
            "decision_pair_success": float("nan"),
        }
    vdcp = sum(row["vdcp_success"] for row in subset) / n
    tie = sum(row["score_tie"] for row in subset) / n
    margin = sum(row["score_margin"] for row in subset) / n
    decision = sum(row["decision_success"] for row in subset) / n
    lo, hi = bootstrap_ci(subset, "vdcp_success") if n else (float("nan"), float("nan"))
    return {
        "detector": detector,
        "transform": transform,
        "pairs": n,
        "vdcp": vdcp,
        "vdcp_ci_low": lo,
        "vdcp_ci_high": hi,
        "mean_score_margin": margin,
        "score_tie_rate": tie,
        "decision_pair_success": decision,
    }


def aggregate_cwe(detector: str, rows: list[dict], min_pairs: int = 5) -> list[dict]:
    by_cwe: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if row["transform"] == "original":
            by_cwe[row["cwe"]].append(row)

    out: list[dict] = []
    for cwe, subset in sorted(by_cwe.items(), key=lambda item: (-len(item[1]), item[0])):
        if len(subset) < min_pairs:
            continue
        n = len(subset)
        out.append(
            {
                "detector": detector,
                "cwe": cwe,
                "pairs": n,
                "vdcp": sum(row["vdcp_success"] for row in subset) / n,
                "mean_score_margin": sum(row["score_margin"] for row in subset) / n,
                "score_tie_rate": sum(row["score_tie"] for row in subset) / n,
                "decision_pair_success": sum(row["decision_success"] for row in subset) / n,
            }
        )
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--metadata", default="data/raw/bigvul.jsonl")
    parser.add_argument("--output", default="results/counterfactual_patch_pair_probe.csv")
    parser.add_argument("--summary", default="results/counterfactual_patch_pair_probe_summary.json")
    parser.add_argument("--cwe-output", default="results/counterfactual_patch_pair_probe_cwe.csv")
    parser.add_argument(
        "--prediction",
        action="append",
        default=None,
        metavar="NAME=PATH",
        help="Prediction JSONL to include. May be repeated. Defaults to the Big-Vul detector list.",
    )
    args = parser.parse_args()

    root = Path(args.root)
    metadata_rows = load_jsonl(root / args.metadata)
    metadata = {row["idx"]: row for row in metadata_rows}
    predictions = DEFAULT_PREDICTIONS
    if args.prediction:
        predictions = []
        for spec in args.prediction:
            if "=" not in spec:
                raise ValueError(f"Invalid --prediction value {spec!r}; expected NAME=PATH")
            name, rel_path = spec.split("=", 1)
            predictions.append((name, rel_path))

    all_pair_rows: list[dict] = []
    all_summary_rows: list[dict] = []
    all_cwe_rows: list[dict] = []
    for detector, rel_path in predictions:
        pair_rows = summarize_rows(detector, load_jsonl(root / rel_path), metadata)
        all_pair_rows.extend(pair_rows)
        all_summary_rows.append(aggregate(detector, pair_rows, "original"))
        all_summary_rows.append(aggregate(detector, pair_rows, "ALL"))
        all_cwe_rows.extend(aggregate_cwe(detector, pair_rows))

    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(all_pair_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_pair_rows)

    summary = root / args.summary
    summary.write_text(json.dumps(all_summary_rows, indent=2), encoding="utf-8")

    cwe_output = root / args.cwe_output
    with cwe_output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(all_cwe_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_cwe_rows)


if __name__ == "__main__":
    main()
