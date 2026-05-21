#!/usr/bin/env python3
"""Create a bounded original+variant evaluation slice for exact public models."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import random


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--origins", type=int, default=120)
    parser.add_argument("--seed", type=int, default=20260518)
    args = parser.parse_args()

    rows = read_jsonl(args.input)
    by_idx: dict[str, list[dict]] = {}
    for row in rows:
        by_idx.setdefault(str(row["idx"]), []).append(row)
    eligible = [idx for idx, group in by_idx.items() if any(row.get("transform") == "original" for row in group)]
    rng = random.Random(args.seed)
    chosen = sorted(rng.sample(eligible, min(args.origins, len(eligible))))
    selected = []
    for idx in chosen:
        group = by_idx[idx]
        selected.extend(sorted(group, key=lambda row: (row.get("transform", ""), row.get("variant_id", ""))))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for row in selected:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({"output": str(args.output), "origins": len(chosen), "rows": len(selected)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
