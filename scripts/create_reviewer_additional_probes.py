#!/usr/bin/env python3
"""Create low-compute reviewer-requested robustness probes.

The generated dataset uses the existing stratified 512-origin CodeXGLUE slice
and adds two kinds of variants:

* small transformation compositions that approximate maintenance edits, and
* identifier-renaming ablations that separate fresh marker names from more
  natural substitute identifiers.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "src"))

from robust_vd import transformations as T  # noqa: E402


COMPOSITIONS = {
    "comp_identifier_renaming__brace_line_shift": ["identifier_renaming", "brace_line_shift"],
    "comp_identifier_renaming__comment_banner": ["identifier_renaming", "comment_banner"],
    "comp_safe_dead_code__code_normalization": ["safe_dead_code_carrier", "code_normalization_abstraction"],
    "comp_dead_branch__identifier_renaming__brace_line_shift": [
        "dead_branch_after_opening_brace",
        "identifier_renaming",
        "brace_line_shift",
    ],
}

IN_VOCAB_NAMES = ("tmp", "count", "idx", "len", "value", "ret", "state", "result")
PROJECT_STYLE_NAMES = ("local_count", "buffer_index", "frame_value", "state_flag", "result_code", "size_value")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def select_origin_ids(slice_path: Path) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for row in read_jsonl(slice_path):
        if row.get("transform") != "original":
            continue
        idx = str(row["idx"])
        if idx not in seen:
            seen.add(idx)
            ids.append(idx)
    return ids


def candidate_identifiers(code: str) -> list[str]:
    candidates: list[str] = []
    local_var_re = re.compile(
        rf"\b(?:const\s+)?(?:unsigned\s+|signed\s+)?(?:{T.TYPE_WORDS})\s+[*\s]*([A-Za-z_][A-Za-z0-9_]*)\s*(?:=|;|,)",
        re.MULTILINE,
    )
    for match in local_var_re.finditer(code):
        name = match.group(1)
        if name not in T.RESERVED_WORDS and not name.startswith("__"):
            candidates.append(name)

    brace = code.find("{")
    paren = code.rfind("(", 0, brace if brace != -1 else len(code))
    if brace != -1 and paren != -1:
        signature = code[paren + 1 : brace]
        param_re = re.compile(
            rf"\b(?:const\s+)?(?:unsigned\s+|signed\s+)?(?:{T.TYPE_WORDS}|[A-Za-z_][A-Za-z0-9_:<>]*)\s+[*&\s]*([A-Za-z_][A-Za-z0-9_]*)\s*(?:,|$)"
        )
        for match in param_re.finditer(signature):
            name = match.group(1)
            if name not in T.RESERVED_WORDS and not name.startswith("__"):
                candidates.append(name)
    return candidates


def rename_with_style(code: str, new_names: tuple[str, ...], transform_name: str) -> T.TransformResult:
    identifiers = set(T.IDENTIFIER_RE.findall(code))
    for candidate in candidate_identifiers(code):
        for new_name in new_names:
            if new_name == candidate or new_name in identifiers:
                continue
            transformed, replacements = T._replace_identifier_outside_protected(code, candidate, new_name)
            if replacements >= 2:
                return T.TransformResult(
                    transform_name,
                    transformed,
                    True,
                    f"renamed {candidate} to {new_name} ({replacements} occurrences)",
                )
    return T.TransformResult(transform_name, code, False, "no collision-free repeated identifier")


def apply_composition(code: str, name: str, steps: list[str]) -> T.TransformResult:
    current = code
    notes: list[str] = []
    changed = False
    for step in steps:
        result = T.TRANSFORMS[step](current)
        current = result.code
        changed = changed or result.changed
        notes.append(f"{step}: {result.validation_note}")
    return T.TransformResult(name, current, changed, " | ".join(notes))


def make_variant(row: dict, name: str, result: T.TransformResult) -> dict:
    return {
        "idx": row["idx"],
        "variant_id": f"{row['idx']}__{name}",
        "transform": name,
        "target": int(row["target"]),
        "func": result.code,
        "changed": result.changed,
        "validation_note": result.validation_note,
        "probe_group": "composition" if name.startswith("comp_") else "identifier_ablation",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-test", type=Path, default=Path("data/raw/codexglue_test.jsonl"))
    parser.add_argument(
        "--slice",
        type=Path,
        default=Path("data/public_exact_slices/codexglue_512origins_stratified_expanded.jsonl"),
    )
    parser.add_argument("--output", type=Path, default=Path("data/processed/codexglue_512_reviewer_probes.jsonl"))
    parser.add_argument("--summary", type=Path, default=Path("data/processed/codexglue_512_reviewer_probes_summary.json"))
    args = parser.parse_args()

    ids = select_origin_ids(args.slice)
    raw_by_idx = {str(row["idx"]): row for row in read_jsonl(args.raw_test)}
    selected = [raw_by_idx[idx] for idx in ids if idx in raw_by_idx]

    rows: list[dict] = []
    for row in selected:
        original = {
            "idx": row["idx"],
            "variant_id": f"{row['idx']}__original",
            "transform": "original",
            "target": int(row["target"]),
            "func": row["func"],
            "changed": False,
            "validation_note": "original sample",
            "probe_group": "original",
        }
        rows.append(original)
        fresh = T.identifier_renaming(row["func"])
        rows.append(make_variant(row, "identifier_renaming_fresh_marker", fresh))
        rows.append(make_variant(row, "identifier_renaming_in_vocab", rename_with_style(row["func"], IN_VOCAB_NAMES, "identifier_renaming_in_vocab")))
        rows.append(make_variant(row, "identifier_renaming_project_style", rename_with_style(row["func"], PROJECT_STYLE_NAMES, "identifier_renaming_project_style")))
        for name, steps in COMPOSITIONS.items():
            rows.append(make_variant(row, name, apply_composition(row["func"], name, steps)))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary: dict[str, dict[str, int]] = {}
    for row in rows:
        transform = row["transform"]
        summary.setdefault(transform, {"n": 0, "changed": 0, "positive": 0})
        summary[transform]["n"] += 1
        summary[transform]["changed"] += int(bool(row["changed"]))
        summary[transform]["positive"] += int(row["target"])
    args.summary.write_text(json.dumps({"origins": len(selected), "rows": len(rows), "by_transform": summary}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "summary": str(args.summary), "origins": len(selected), "rows": len(rows)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
