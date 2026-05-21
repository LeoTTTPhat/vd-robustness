#!/usr/bin/env python3
"""Lightweight automated validation checks for transformed variants."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def brace_balance(code: str) -> bool:
    balance = 0
    for ch in code:
        if ch == "{":
            balance += 1
        elif ch == "}":
            balance -= 1
            if balance < 0:
                return False
    return balance == 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    original_by_idx: dict[str, dict] = {}
    variants_by_transform: dict[str, list[dict]] = defaultdict(list)
    for row in read_jsonl(args.input):
        if row["transform"] == "original":
            original_by_idx[str(row["idx"])] = row
        else:
            variants_by_transform[row["transform"]].append(row)

    summary = {"file": str(args.input), "transforms": {}}
    for transform, rows in sorted(variants_by_transform.items()):
        counts = Counter()
        for row in rows:
            original = original_by_idx.get(str(row["idx"]))
            counts["rows"] += 1
            counts["changed"] += int(bool(row.get("changed")))
            counts["label_preserved"] += int(original is not None and original.get("target") == row.get("target"))
            counts["has_opening_brace"] += int("{" in row.get("func", ""))
            counts["balanced_braces"] += int(brace_balance(row.get("func", "")))
            counts["nonempty"] += int(bool(row.get("func", "").strip()))
        total = counts["rows"]
        summary["transforms"][transform] = {
            **dict(counts),
            "changed_rate": counts["changed"] / total if total else 0,
            "label_preservation_rate": counts["label_preserved"] / total if total else 0,
            "brace_balance_rate": counts["balanced_braces"] / total if total else 0,
        }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

