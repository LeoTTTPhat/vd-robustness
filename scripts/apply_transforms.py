#!/usr/bin/env python3
"""Apply robustness transformations to a JSONL vulnerability dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from robust_vd.transformations import apply_all


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_no}: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--transforms", nargs="*", default=None)
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with args.output.open("w", encoding="utf-8") as out:
        for row in read_jsonl(args.input):
            idx = row.get("idx")
            code = row.get("func") or row.get("code")
            if idx is None or code is None:
                raise ValueError("Each row must contain idx and func/code fields.")

            original = {
                "idx": idx,
                "variant_id": f"{idx}__original",
                "transform": "original",
                "target": row.get("target"),
                "func": code,
                "changed": False,
                "validation_note": "original sample",
            }
            out.write(json.dumps(original, ensure_ascii=False) + "\n")
            count += 1

            for result in apply_all(code, args.transforms):
                variant = {
                    "idx": idx,
                    "variant_id": f"{idx}__{result.name}",
                    "transform": result.name,
                    "target": row.get("target"),
                    "func": result.code,
                    "changed": result.changed,
                    "validation_note": result.validation_note,
                }
                out.write(json.dumps(variant, ensure_ascii=False) + "\n")
                count += 1

    print(f"Wrote {count} variants to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

