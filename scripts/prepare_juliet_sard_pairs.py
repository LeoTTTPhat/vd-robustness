#!/usr/bin/env python3
"""Prepare a bounded Juliet/SARD before/after pair sample.

The extractor uses construction-guaranteed Juliet C/C++ test cases where a
``*_bad`` file has a matching ``*_goodB2G`` or ``*_goodG2B`` file. The output is
the same JSONL schema used by the Big-Vul counterfactual probe: vulnerable
``*-before`` rows and patched/non-vulnerable ``*-after`` rows.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import zipfile
from collections import defaultdict
from pathlib import Path


CWE_RE = re.compile(r"/(CWE\d+)[_/]")
PAIR_RE = re.compile(r"^(?P<stem>.+)_(?P<kind>bad|goodB2G|goodG2B)\.(?P<ext>c|cpp)$")
FUNC_RE = re.compile(
    r"(?:static\s+)?(?:void|int|char\s*\*|wchar_t\s*\*|size_t|long|short|double|float)\s+"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*(?:_bad)?|goodG2B|goodB2G)\s*\([^;{}]*\)\s*\{",
    re.MULTILINE,
)


def clean_code(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    for line in text.splitlines():
        if "#include" in line and "std_testcase" in line:
            continue
        if line.strip().startswith("#pragma"):
            continue
        lines.append(line)
    return "\n".join(lines).strip() + "\n"


def extract_function(text: str, wanted: str) -> str | None:
    for match in FUNC_RE.finditer(text):
        name = match.group("name")
        if wanted == "bad" and not name.endswith("_bad"):
            continue
        if wanted != "bad" and name != wanted:
            continue
        depth = 0
        for pos in range(match.end() - 1, len(text)):
            if text[pos] == "{":
                depth += 1
            elif text[pos] == "}":
                depth -= 1
                if depth == 0:
                    return text[match.start() : pos + 1]
    return None


def choose_pairs(zip_path: Path, max_pairs: int, per_cwe: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    by_cwe: dict[str, list[dict]] = defaultdict(list)
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            if "/testcases/" not in name or name.endswith("/"):
                continue
            filename = Path(name).name
            cwe_match = CWE_RE.search(name)
            if not cwe_match:
                continue
            cwe = cwe_match.group(1)
            match = PAIR_RE.match(filename)
            if match and match.group("ext") == "cpp":
                continue
            if not filename.endswith(".c"):
                continue
            text = zf.read(name).decode("utf-8", errors="ignore")
            bad_code = extract_function(text, "bad")
            good_code = extract_function(text, "goodG2B") or extract_function(text, "goodB2G")
            if bad_code and good_code:
                by_cwe[cwe].append(
                    {
                        "cwe": cwe,
                        "stem": Path(name).stem,
                        "bad_path": name,
                        "good_path": name,
                        "bad_code": bad_code,
                        "good_code": good_code,
                    }
                )

    pairs: list[dict] = []
    for cwe in sorted(by_cwe):
        cwe_pairs = by_cwe[cwe]
        rng.shuffle(cwe_pairs)
        pairs.extend(cwe_pairs[:per_cwe])

    rng.shuffle(pairs)
    return pairs[:max_pairs]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", type=Path, default=Path("data/sources/juliet_sard/Juliet_Test_Suite_v1.3_for_C_Cpp.zip"))
    parser.add_argument("--output", type=Path, default=Path("data/raw/juliet_sard_pairs.jsonl"))
    parser.add_argument("--summary", type=Path, default=Path("data/processed/juliet_sard_pairs_summary.json"))
    parser.add_argument("--max-pairs", type=int, default=400)
    parser.add_argument("--per-cwe", type=int, default=12)
    parser.add_argument("--seed", type=int, default=20260523)
    args = parser.parse_args()

    selected = choose_pairs(args.zip, args.max_pairs, args.per_cwe, args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.summary.parent.mkdir(parents=True, exist_ok=True)

    cwe_counts: dict[str, int] = defaultdict(int)
    with args.output.open("w", encoding="utf-8") as out:
        for ordinal, pair in enumerate(selected, 1):
            cwe = pair["cwe"]
            base = f"juliet-{cwe}-{ordinal:04d}"
            bad_code = clean_code(pair["bad_code"])
            good_code = clean_code(pair["good_code"])
            if not bad_code.strip() or not good_code.strip():
                continue
            cwe_counts[cwe] += 1
            common = {
                "pair_id": base,
                "cwe": cwe,
                "juliet_stem": pair["stem"],
                "source": "Juliet/SARD C/C++ v1.3",
            }
            out.write(
                json.dumps(
                    {
                        **common,
                        "idx": f"{base}-before",
                        "side": "before",
                        "target": 1,
                        "func": bad_code,
                        "source_path": pair["bad_path"],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            out.write(
                json.dumps(
                    {
                        **common,
                        "idx": f"{base}-after",
                        "side": "after",
                        "target": 0,
                        "func": good_code,
                        "source_path": pair["good_path"],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    args.summary.write_text(
        json.dumps(
            {
                "source_zip": str(args.zip),
                "output": str(args.output),
                "pairs": sum(cwe_counts.values()),
                "rows": 2 * sum(cwe_counts.values()),
                "cwe_count": len(cwe_counts),
                "per_cwe_cap": args.per_cwe,
                "max_pairs": args.max_pairs,
                "cwe_counts": dict(sorted(cwe_counts.items())),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"pairs": sum(cwe_counts.values()), "cwes": len(cwe_counts), "output": str(args.output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
