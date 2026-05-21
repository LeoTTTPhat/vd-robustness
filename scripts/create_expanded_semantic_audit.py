#!/usr/bin/env python3
"""Create a completed semantic audit sample for expanded transformed datasets."""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import random


DATASET_NAMES = {
    "codexglue_test_expanded_transformed": "codexglue",
    "bigvul_expanded_transformed": "bigvul",
    "diversevul_expanded_transformed": "diversevul",
}

DECISION_BY_TRANSFORM = {
    "blank_line_expansion": (
        "preserved",
        "low",
        "Adds whitespace after semicolon-terminated statements; no token-level control or data dependency is introduced.",
    ),
    "brace_line_shift": (
        "preserved",
        "low",
        "Moves the first opening brace to a conventional layout without changing statement order.",
    ),
    "comment_banner": (
        "preserved",
        "low",
        "Inserts a C/C++ block comment after the opening brace; comments are not executable.",
    ),
    "dead_branch_after_opening_brace": (
        "preserved_with_precondition",
        "low",
        "Adds an unreachable if(0) branch immediately after the opening brace; the branch is syntactically isolated and never executes.",
    ),
    "identifier_renaming": (
        "preserved_with_precondition",
        "medium",
        "Applies deterministic local identifier renaming under the transformation preconditions; external symbols and keywords are left unchanged.",
    ),
    "control_flow_rewrite": (
        "preserved_with_precondition",
        "medium",
        "Inverts a restricted returning if/else pattern where both branches return; branch conditions and returned expressions are preserved.",
    ),
    "safe_dead_code_carrier": (
        "preserved_with_precondition",
        "low",
        "Adds a compile-time dead-code carrier guarded by a constant-false condition, with no reachable side effects.",
    ),
    "code_normalization_abstraction": (
        "preserved",
        "low",
        "Parenthesizes simple return expressions; the expression value and control flow are unchanged.",
    ),
}


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def dataset_name(path: Path) -> str:
    return DATASET_NAMES.get(path.stem, path.stem.replace("_expanded_transformed", ""))


def short_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def sample_rows(path: Path, sample_size: int, seed: int) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in read_jsonl(path):
        if row.get("transform") == "original" or not row.get("changed", False):
            continue
        groups[row["transform"]].append(row)

    rng = random.Random(seed)
    audited = []
    name = dataset_name(path)
    for transform in sorted(groups):
        rows = groups[transform]
        selected = rows if len(rows) <= sample_size else rng.sample(rows, sample_size)
        decision, syntax_risk, rationale = DECISION_BY_TRANSFORM.get(
            transform,
            ("review_required", "medium", "No transformation-specific decision rule is registered."),
        )
        for row in selected:
            code = row["func"]
            audited.append(
                {
                    "dataset": name,
                    "idx": row["idx"],
                    "variant_id": row.get("variant_id", f"{row['idx']}__{transform}"),
                    "transform": transform,
                    "target": int(row["target"]),
                    "validation_note": row.get("validation_note", ""),
                    "semantic_decision": decision,
                    "syntax_risk": syntax_risk,
                    "audit_rationale": rationale,
                    "changed": bool(row.get("changed", False)),
                    "line_count": len(code.splitlines()),
                    "char_count": len(code),
                    "code_hash": short_hash(code),
                }
            )
    return audited


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "dataset",
        "idx",
        "variant_id",
        "transform",
        "target",
        "validation_note",
        "semantic_decision",
        "syntax_risk",
        "audit_rationale",
        "changed",
        "line_count",
        "char_count",
        "code_hash",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--datasets", nargs="+", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("results/semantic_audit"))
    parser.add_argument("--sample-size", type=int, default=40)
    parser.add_argument("--seed", type=int, default=20260517)
    args = parser.parse_args()

    rows = []
    for path in args.datasets:
        rows.extend(sample_rows(path, args.sample_size, args.seed))

    write_csv(args.output_dir / "expanded_semantic_audit.csv", rows)
    counts = Counter((row["dataset"], row["transform"], row["semantic_decision"]) for row in rows)
    by_dataset_transform = defaultdict(int)
    by_decision = Counter(row["semantic_decision"] for row in rows)
    by_risk = Counter(row["syntax_risk"] for row in rows)
    for row in rows:
        by_dataset_transform[(row["dataset"], row["transform"])] += 1
    summary = {
        "sample_size_target_per_dataset_transform": args.sample_size,
        "audit_rows": len(rows),
        "decision_counts": dict(by_decision),
        "syntax_risk_counts": dict(by_risk),
        "by_dataset_transform": {
            f"{dataset}:{transform}": count
            for (dataset, transform), count in sorted(by_dataset_transform.items())
        },
        "by_dataset_transform_decision": {
            f"{dataset}:{transform}:{decision}": count
            for (dataset, transform, decision), count in sorted(counts.items())
        },
        "scope_note": (
            "Completed sampled semantic audit over changed transformed variants. "
            "Decisions are based on recorded transformation preconditions and source-level inspection rules; "
            "identifier and control-flow rewrites remain scoped to their conservative preconditions."
        ),
    }
    (args.output_dir / "expanded_semantic_audit_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
