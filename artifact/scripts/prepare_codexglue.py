#!/usr/bin/env python3
"""Download and normalize CodeXGLUE/Devign defect-detection splits.

The Hugging Face mirror stores this dataset as Parquet. This script converts it
to the JSONL schema used by this study:

  {"idx": 1, "func": "...", "target": 0}
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen

import pyarrow.parquet as pq


DATASET = "google/code_x_glue_cc_defect_detection"
BASE_URL = f"https://huggingface.co/datasets/{DATASET}/resolve/main/data"
SPLITS = {
    "train": "train-00000-of-00001.parquet",
    "validation": "validation-00000-of-00001.parquet",
    "test": "test-00000-of-00001.parquet",
}


def download(url: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and output.stat().st_size > 0:
        return
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=120) as response:
        output.write_bytes(response.read())


def normalize_target(value) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "vulnerable", "insecure"}:
        return 1
    if text in {"false", "0", "no", "secure"}:
        return 0
    raise ValueError(f"Cannot normalize target value: {value!r}")


def normalize_split(parquet_path: Path, jsonl_path: Path) -> dict:
    table = pq.read_table(parquet_path)
    rows = table.to_pylist()
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)

    if not rows:
        raise ValueError(f"No rows in {parquet_path}")

    columns = set(rows[0])
    if "func" not in columns:
        raise ValueError(f"Expected a 'func' column in {parquet_path}; found {sorted(columns)}")
    if "target" not in columns:
        raise ValueError(f"Expected a 'target' column in {parquet_path}; found {sorted(columns)}")

    vulnerable = 0
    secure = 0
    lengths: list[int] = []
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for row_no, row in enumerate(rows):
            idx = row.get("idx", row.get("id", row_no))
            func = row["func"]
            target = normalize_target(row["target"])
            vulnerable += target
            secure += 1 - target
            lengths.append(len(func))
            out = {"idx": int(idx), "func": func, "target": target}
            handle.write(json.dumps(out, ensure_ascii=False) + "\n")

    return {
        "rows": len(rows),
        "secure": secure,
        "vulnerable": vulnerable,
        "vulnerable_ratio": vulnerable / len(rows),
        "min_chars": min(lengths),
        "median_chars": sorted(lengths)[len(lengths) // 2],
        "max_chars": max(lengths),
        "columns": sorted(columns),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--source-dir", type=Path, default=Path("data/sources/codexglue"))
    parser.add_argument("--summary", type=Path, default=Path("data/processed/codexglue_summary.json"))
    args = parser.parse_args()

    summary = {
        "dataset": DATASET,
        "source_base_url": BASE_URL,
        "splits": {},
    }

    for split, filename in SPLITS.items():
        parquet_path = args.source_dir / filename
        jsonl_path = args.raw_dir / f"codexglue_{split}.jsonl"
        download(f"{BASE_URL}/{filename}", parquet_path)
        split_summary = normalize_split(parquet_path, jsonl_path)
        split_summary["parquet_file"] = str(parquet_path)
        split_summary["jsonl_file"] = str(jsonl_path)
        summary["splits"][split] = split_summary

    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
