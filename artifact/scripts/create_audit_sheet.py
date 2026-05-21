#!/usr/bin/env python3
"""Create a manual audit sheet for transformed variants."""

from __future__ import annotations

import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--samples-per-transform", type=int, default=30)
    parser.add_argument("--seed", type=int, default=20260517)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    by_transform: dict[str, list[dict]] = defaultdict(list)
    for row in read_jsonl(args.input):
        if row.get("transform") != "original" and row.get("changed"):
            by_transform[row["transform"]].append(row)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "idx",
        "variant_id",
        "transform",
        "target",
        "validation_note",
        "valid_syntax",
        "preserves_semantics",
        "exclude",
        "auditor_notes",
        "func_excerpt",
    ]
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for transform, rows in sorted(by_transform.items()):
            sample = rows if len(rows) <= args.samples_per_transform else rng.sample(rows, args.samples_per_transform)
            for row in sample:
                func = row["func"].replace("\r\n", "\n")
                writer.writerow(
                    {
                        "idx": row["idx"],
                        "variant_id": row["variant_id"],
                        "transform": transform,
                        "target": row.get("target"),
                        "validation_note": row.get("validation_note", ""),
                        "valid_syntax": "",
                        "preserves_semantics": "",
                        "exclude": "",
                        "auditor_notes": "",
                        "func_excerpt": func[:800].replace("\n", "\\n"),
                    }
                )

    print(f"Wrote audit sheet to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

