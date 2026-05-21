#!/usr/bin/env python3
"""Normalize Big-Vul and DiverseVul for transformation-robustness experiments.

The script intentionally uses the Hugging Face dataset rows API by default.
That keeps the setup lightweight and avoids requiring the full `datasets`
package or a complete local mirror before a pilot can be conducted.

Output schema:
  idx, func, target, project, commit_id, cwe, source_dataset, source_split
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DATASETS = {
    "bigvul": {
        "repo": "bstee615/bigvul",
        "splits": ["train", "validation", "test"],
        "local_globs": ["bigvul_hf/data/*.parquet", "bigvul/*.parquet"],
    },
    "diversevul": {
        "repo": "bstee615/diversevul",
        "splits": ["train", "validation", "test"],
        "local_globs": ["diversevul_hf/data/*.parquet", "diversevul/*.parquet"],
    },
}


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def first_present(row: dict, names: list[str], default=None):
    for name in names:
        if name in row and row[name] not in (None, "", [], {}):
            return row[name]
    return default


def cwe_text(value) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, list):
        return ";".join(str(item) for item in value) if value else "unknown"
    return str(value)


def api_rows(repo: str, splits: list[str], page_size: int, max_raw_rows: int | None):
    raw_count = 0
    for split in splits:
        offset = 0
        while True:
            params = urlencode(
                {
                    "dataset": repo,
                    "config": "default",
                    "split": split,
                    "offset": offset,
                    "length": page_size,
                }
            )
            url = f"https://datasets-server.huggingface.co/rows?{params}"
            request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            payload = None
            for attempt in range(6):
                try:
                    with urlopen(request, timeout=120) as response:
                        payload = json.load(response)
                    break
                except HTTPError as exc:
                    if exc.code != 429 or attempt == 5:
                        raise
                    wait = 10 * (attempt + 1)
                    print(f"{repo}:{split} rate-limited; waiting {wait}s", flush=True)
                    time.sleep(wait)
                except URLError:
                    if attempt == 5:
                        raise
                    wait = 5 * (attempt + 1)
                    print(f"{repo}:{split} transient network error; waiting {wait}s", flush=True)
                    time.sleep(wait)
            if payload is None:
                raise RuntimeError(f"Could not fetch rows for {repo}:{split} at offset {offset}")
            rows = payload.get("rows", [])
            total = int(payload.get("num_rows_total", 0))
            if not rows:
                break
            for item in rows:
                row = dict(item["row"])
                row["_source_split"] = split
                row["_row_idx"] = item.get("row_idx")
                yield row
                raw_count += 1
                if max_raw_rows and raw_count >= max_raw_rows:
                    return
            offset += len(rows)
            print(f"{repo}:{split} fetched {offset}/{total}", flush=True)
            if offset >= total:
                break
            time.sleep(0.05)


def parquet_rows(paths: list[Path], max_raw_rows: int | None):
    try:
        import pyarrow.parquet as pq
    except Exception as exc:  # pragma: no cover - optional dependency branch.
        raise SystemExit("Reading local parquet files requires pyarrow.") from exc

    raw_count = 0
    for path in paths:
        print(f"reading {path}", flush=True)
        table = pq.read_table(path)
        for row in table.to_pylist():
            row["_source_split"] = infer_split(path)
            row["_row_idx"] = raw_count
            yield row
            raw_count += 1
            if max_raw_rows and raw_count >= max_raw_rows:
                return


def infer_split(path: Path) -> str:
    name = path.name.lower()
    for split in ("train", "validation", "test"):
        if name.startswith(split):
            return split
    return "unknown"


def local_parquet_paths(source_dir: Path, name: str) -> list[Path]:
    paths: list[Path] = []
    for pattern in DATASETS[name]["local_globs"]:
        paths.extend(sorted(source_dir.glob(pattern)))
    good = []
    for path in paths:
        if path.exists() and path.stat().st_size > 0:
            good.append(path)
    return good


def normalize_bigvul(row: dict) -> list[dict]:
    split = row.get("_source_split", "unknown")
    row_idx = row.get("_row_idx", "unknown")
    commit = first_present(row, ["commit_id"], f"row{row_idx}")
    project = first_present(row, ["project"], "unknown")
    cwe = cwe_text(first_present(row, ["CWE ID"], "unknown"))
    rows: list[dict] = []

    before = first_present(row, ["func_before"])
    after = first_present(row, ["func_after"])
    vul = int(first_present(row, ["vul"], 0) or 0)

    if before and vul == 1:
        rows.append(
            {
                "idx": f"bigvul-{commit}-{row_idx}-before",
                "func": str(before),
                "target": 1,
                "project": str(project),
                "commit_id": str(commit),
                "cwe": cwe,
                "source_dataset": "Big-Vul",
                "source_split": split,
            }
        )
    if after:
        rows.append(
            {
                "idx": f"bigvul-{commit}-{row_idx}-after",
                "func": str(after),
                "target": 0,
                "project": str(project),
                "commit_id": str(commit),
                "cwe": cwe,
                "source_dataset": "Big-Vul",
                "source_split": split,
            }
        )
    elif before and vul == 0:
        rows.append(
            {
                "idx": f"bigvul-{commit}-{row_idx}-nonvul",
                "func": str(before),
                "target": 0,
                "project": str(project),
                "commit_id": str(commit),
                "cwe": cwe,
                "source_dataset": "Big-Vul",
                "source_split": split,
            }
        )
    return rows


def normalize_diversevul(row: dict) -> list[dict]:
    func = first_present(row, ["func"])
    if not func:
        return []
    split = row.get("_source_split", "unknown")
    row_idx = row.get("_row_idx", "unknown")
    commit = first_present(row, ["commit_id", "hash"], f"row{row_idx}")
    return [
        {
            "idx": f"diversevul-{commit}-{row_idx}",
            "func": str(func),
            "target": int(first_present(row, ["target"], 0) or 0),
            "project": str(first_present(row, ["project"], "unknown")),
            "commit_id": str(commit),
            "cwe": cwe_text(first_present(row, ["cwe"], "unknown")),
            "source_dataset": "DiverseVul",
            "source_split": split,
        }
    ]


def summarize(rows: list[dict], dataset: str, output: Path, raw_rows: int, skipped: int, source_access: str) -> dict:
    labels = Counter(int(row["target"]) for row in rows)
    splits = Counter(row.get("source_split", "unknown") for row in rows)
    projects = {row.get("project", "unknown") for row in rows}
    cwes = {row.get("cwe", "unknown") for row in rows}
    chars = sorted(len(row["func"]) for row in rows)
    median_chars = chars[len(chars) // 2] if chars else 0
    return {
        "dataset": dataset,
        "raw_rows_read": raw_rows,
        "normalized_rows": len(rows),
        "skipped_raw_rows": skipped,
        "vulnerable": labels.get(1, 0),
        "non_vulnerable": labels.get(0, 0),
        "vulnerable_ratio": labels.get(1, 0) / len(rows) if rows else 0,
        "split_counts": dict(sorted(splits.items())),
        "project_count": len(projects),
        "cwe_count": len(cwes),
        "median_chars": median_chars,
        "output": str(output),
        "source_access": source_access,
    }


def prepare_dataset(
    name: str,
    source_dir: Path,
    output: Path,
    summary_path: Path,
    max_rows: int,
    page_size: int,
    max_raw_rows: int | None,
    use_local_parquet: bool,
) -> dict:
    spec = DATASETS[name]
    normalizer = normalize_bigvul if name == "bigvul" else normalize_diversevul
    rows: list[dict] = []
    raw_rows = 0
    skipped = 0
    source_access = "huggingface_dataset_rows_api"
    row_iter = api_rows(spec["repo"], spec["splits"], page_size, max_raw_rows)

    if use_local_parquet:
        paths = local_parquet_paths(source_dir, name)
        if not paths:
            raise FileNotFoundError(f"No local parquet files found for {name} under {source_dir}")
        row_iter = parquet_rows(paths, max_raw_rows)
        source_access = "local_huggingface_parquet"

    for raw in row_iter:
        raw_rows += 1
        normalized = normalizer(raw)
        if not normalized:
            skipped += 1
            continue
        for row in normalized:
            rows.append(row)
            if len(rows) >= max_rows:
                break
        if len(rows) >= max_rows:
            break

    write_jsonl(output, rows)
    summary = summarize(rows, name, output, raw_rows, skipped, source_access)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", choices=["bigvul", "diversevul", "all"], default="all")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--summary-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--source-dir", type=Path, default=Path("data/sources"))
    parser.add_argument("--use-local-parquet", action="store_true")
    parser.add_argument("--bigvul-max-rows", type=int, default=3000)
    parser.add_argument("--diversevul-max-rows", type=int, default=5000)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--max-raw-rows", type=int)
    args = parser.parse_args()

    names = ["bigvul", "diversevul"] if args.dataset == "all" else [args.dataset]
    for name in names:
        max_rows = args.bigvul_max_rows if name == "bigvul" else args.diversevul_max_rows
        prepare_dataset(
            name,
            args.source_dir,
            args.raw_dir / f"{name}.jsonl",
            args.summary_dir / f"{name}_summary.json",
            max_rows,
            args.page_size,
            args.max_raw_rows,
            args.use_local_parquet,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
