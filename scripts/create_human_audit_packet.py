#!/usr/bin/env python3
"""Create a human-annotation packet with original/transformed code pairs."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
import json
from pathlib import Path
import random


DATASET_NAMES = {
    "codexglue_test_expanded_transformed": "codexglue",
    "bigvul_expanded_transformed": "bigvul",
    "diversevul_expanded_transformed": "diversevul",
}


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def dataset_name(path: Path) -> str:
    return DATASET_NAMES.get(path.stem, path.stem.replace("_expanded_transformed", ""))


def sample_packet(path: Path, sample_size: int, seed: int) -> list[dict]:
    originals = {}
    variants = defaultdict(list)
    for row in read_jsonl(path):
        if row.get("transform") == "original":
            originals[str(row["idx"])] = row
        elif row.get("changed", False):
            variants[row["transform"]].append(row)
    rng = random.Random(seed)
    rows = []
    for transform in sorted(variants):
        candidates = variants[transform]
        selected = candidates if len(candidates) <= sample_size else rng.sample(candidates, sample_size)
        for row in selected:
            original = originals.get(str(row["idx"]), {})
            rows.append(
                {
                    "dataset": dataset_name(path),
                    "idx": row["idx"],
                    "variant_id": row.get("variant_id", f"{row['idx']}__{transform}"),
                    "transform": transform,
                    "target": int(row["target"]),
                    "validation_note": row.get("validation_note", ""),
                    "original_code": original.get("func", ""),
                    "transformed_code": row.get("func", ""),
                    "annotator1_label": "",
                    "annotator1_notes": "",
                    "annotator2_label": "",
                    "annotator2_notes": "",
                    "adjudicated_label": "",
                    "adjudication_notes": "",
                }
            )
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "dataset",
        "idx",
        "variant_id",
        "transform",
        "target",
        "validation_note",
        "original_code",
        "transformed_code",
        "annotator1_label",
        "annotator1_notes",
        "annotator2_label",
        "annotator2_notes",
        "adjudicated_label",
        "adjudication_notes",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--datasets", nargs="+", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=Path("results/semantic_audit/human_semantic_audit_packet.csv"))
    parser.add_argument("--sample-size", type=int, default=40)
    parser.add_argument("--seed", type=int, default=20260518)
    args = parser.parse_args()
    rows = []
    for path in args.datasets:
        rows.extend(sample_packet(path, args.sample_size, args.seed))
    write_csv(args.output, rows)
    summary = {
        "rows": len(rows),
        "sample_size_target": args.sample_size,
        "status": "annotation_packet_created_not_yet_human_annotated",
        "protocol": "docs/human_semantic_audit_protocol.md",
    }
    args.output.with_suffix(".summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
