#!/usr/bin/env python3
"""Authenticated parallel downloader for Hugging Face dataset parquet files."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from pathlib import Path
import subprocess
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen


DATASETS = {
    "cvefixes": (
        "Shrutz72/cvefixes",
        [
            "data/train-00000-of-00003.parquet",
            "data/train-00001-of-00003.parquet",
            "data/train-00002-of-00003.parquet",
        ],
    ),
    "diversevul": (
        "bstee615/diversevul",
        [
            "data/train-00000-of-00002-06b0cca04c9bb0f2.parquet",
            "data/train-00001-of-00002-0fb7d9c1c879fb27.parquet",
            "data/validation-00000-of-00001-4e4cf40ca95c048a.parquet",
            "data/test-00000-of-00001-467ddf31930d18ee.parquet",
        ],
    ),
}


def remote_size(url: str, token: str) -> int:
    headers = {"Authorization": f"Bearer {token}", "User-Agent": "Mozilla/5.0"}
    request = Request(url, headers=headers, method="HEAD")
    with urlopen(request, timeout=120) as response:
        return int(response.headers["Content-Length"])


def download_range(url: str, token: str, start: int, end: int, part: Path) -> int:
    if part.exists() and part.stat().st_size == end - start + 1:
        return part.stat().st_size
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "Mozilla/5.0",
        "Range": f"bytes={start}-{end}",
    }
    request = Request(url, headers=headers)
    tmp = part.with_suffix(part.suffix + ".tmp")
    with urlopen(request, timeout=240) as response:
        status = getattr(response, "status", None)
        if status not in (200, 206):
            raise HTTPError(url, status, f"unexpected status {status}", response.headers, None)
        with tmp.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
    tmp.replace(part)
    return part.stat().st_size


def merge_parts(parts: list[Path], output: Path, expected_size: int) -> None:
    tmp = output.with_suffix(output.suffix + ".tmp")
    with tmp.open("wb") as out:
        for part in parts:
            with part.open("rb") as handle:
                while True:
                    chunk = handle.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
    if tmp.stat().st_size != expected_size:
        raise ValueError(f"merged size mismatch for {output}: {tmp.stat().st_size} != {expected_size}")
    tmp.replace(output)
    for part in parts:
        part.unlink(missing_ok=True)


def validate_parquet(path: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import pyarrow.parquet as pq, sys; pq.ParquetFile(sys.argv[1]); print('valid', sys.argv[1])",
            str(path),
        ],
        check=True,
    )


def download_file(repo: str, filename: str, output: Path, token: str, workers: int, chunk_mb: int) -> None:
    url = f"https://huggingface.co/datasets/{repo}/resolve/main/{filename}"
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        try:
            validate_parquet(output)
            print(f"exists valid {output} {output.stat().st_size}", flush=True)
            return
        except Exception:
            print(f"replacing incomplete {output}", flush=True)
            output.unlink(missing_ok=True)
    size = remote_size(url, token)
    chunk = chunk_mb * 1024 * 1024
    ranges = [(start, min(start + chunk - 1, size - 1)) for start in range(0, size, chunk)]
    part_dir = output.parent / f".{output.name}.parts"
    part_dir.mkdir(parents=True, exist_ok=True)
    parts = [part_dir / f"part-{i:04d}" for i in range(len(ranges))]
    print(f"downloading {output} size={size} parts={len(parts)} workers={workers}", flush=True)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(download_range, url, token, start, end, part): (i, start, end, part)
            for i, ((start, end), part) in enumerate(zip(ranges, parts))
        }
        done = 0
        for future in as_completed(futures):
            i, start, end, part = futures[future]
            bytes_written = future.result()
            done += 1
            print(f"  part {i + 1}/{len(parts)} {bytes_written} bytes", flush=True)
    merge_parts(parts, output, size)
    part_dir.rmdir()
    validate_parquet(output)
    print(f"wrote {output} {output.stat().st_size}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", choices=["cvefixes", "diversevul", "all"], default="all")
    parser.add_argument("--output-root", type=Path, default=Path("data/sources"))
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--chunk-mb", type=int, default=16)
    args = parser.parse_args()
    token = os.environ.get("HF_TOKEN")
    if not token:
        raise SystemExit("HF_TOKEN environment variable is required")
    names = ["cvefixes", "diversevul"] if args.dataset == "all" else [args.dataset]
    for name in names:
        repo, files = DATASETS[name]
        for filename in files:
            output = args.output_root / f"{name}_hf" / filename
            download_file(repo, filename, output, token, args.workers, args.chunk_mb)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
