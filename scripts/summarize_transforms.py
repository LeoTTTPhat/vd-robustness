#!/usr/bin/env python3
"""Summarize transformed JSONL variants."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    rows = [
        json.loads(line)
        for line in args.input.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    by_transform = Counter(row["transform"] for row in rows)
    changed = Counter(row["transform"] for row in rows if row.get("changed"))
    labels: dict[str, Counter] = defaultdict(Counter)
    notes: dict[str, Counter] = defaultdict(Counter)

    for row in rows:
        transform = row["transform"]
        labels[transform][str(row.get("target"))] += 1
        notes[transform][row.get("validation_note", "")] += 1

    summary = {
        "file": str(args.input),
        "total_rows": len(rows),
        "original_samples": by_transform.get("original", 0),
        "transformed_rows": len(rows) - by_transform.get("original", 0),
        "transforms": {},
    }

    for transform in sorted(by_transform):
        count = by_transform[transform]
        summary["transforms"][transform] = {
            "rows": count,
            "changed_rows": changed[transform],
            "unchanged_rows": count - changed[transform],
            "applicability_rate": None if transform == "original" else changed[transform] / count,
            "target_counts": dict(labels[transform]),
            "validation_notes": dict(notes[transform]),
        }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

