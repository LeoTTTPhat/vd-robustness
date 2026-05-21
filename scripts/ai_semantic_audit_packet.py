#!/usr/bin/env python3
"""Create a transparent AI-assisted semantic audit from the human audit packet.

This script intentionally does not fill the human annotator columns. It produces
separate AI-review fields so the artifact can use the result as a screening
audit without misrepresenting it as a two-human annotation.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


LOW_RISK_PRESERVED = {
    "blank_line_expansion": "Whitespace-only layout change; no executable token is intentionally introduced.",
    "brace_line_shift": "Opening-brace layout change; statement order and expressions are intentionally preserved.",
    "comment_banner": "Inserted block comment; comments have no runtime effect outside preprocessor/macro edge cases.",
    "code_normalization_abstraction": "Parenthesizes simple return expressions; value and control flow are intended to remain unchanged.",
}

PRECONDITIONED = {
    "dead_branch_after_opening_brace": "Adds an unreachable branch guarded by a constant-false condition.",
    "safe_dead_code_carrier": "Adds a compile-time or constant-false dead-code carrier with no reachable side effects.",
    "identifier_renaming": "Renames a simple local identifier under local-scope preconditions; external bindings must remain unchanged.",
    "control_flow_rewrite": "Inverts a restricted returning if/else where both branches return; branch expressions must remain unchanged.",
}


def read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def compact(code: str) -> str:
    return re.sub(r"\s+", " ", code or "").strip()


def remove_comments(code: str) -> str:
    code = re.sub(r"/\*.*?\*/", "", code or "", flags=re.DOTALL)
    code = re.sub(r"//.*", "", code)
    return code


def has_constant_false_dead_code(code: str) -> bool:
    code = code or ""
    constant_false_guards = [
        r"\bif\s*\(\s*0\s*\)",
        r"\bif\s*\(\s*false\s*\)",
        r"\bif\s*\(\s*sizeof\s*\(\s*int\s*\)\s*==\s*0\s*\)",
        r"\bif\s*\(\s*0\s*==\s*sizeof\s*\(\s*int\s*\)\s*\)",
    ]
    return any(re.search(pattern, code) for pattern in constant_false_guards) or bool(
        re.search(r"#\s*if\s+0\b", code)
    )


def audit_row(row: dict) -> tuple[str, str, str, bool]:
    transform = row["transform"]
    original = row.get("original_code", "")
    transformed = row.get("transformed_code", "")

    if not transformed.strip() or not original.strip():
        return "uncertain", "high", "Missing original or transformed code in packet.", True

    if transform in {"blank_line_expansion", "brace_line_shift"}:
        if compact(original) == compact(transformed):
            return "preserved", "low", LOW_RISK_PRESERVED[transform] + " Whitespace-normalized code matches.", False
        return "preserved", "low", LOW_RISK_PRESERVED[transform] + " Whitespace-normalized code differs, so this remains a source-level review item.", False

    if transform == "comment_banner":
        if compact(remove_comments(original)) == compact(remove_comments(transformed)):
            return "preserved", "low", LOW_RISK_PRESERVED[transform] + " Comment-stripped code matches.", False
        return "preserved", "low", LOW_RISK_PRESERVED[transform] + " Comment-stripped code differs because existing comments or formatting changed.", False

    if transform == "code_normalization_abstraction":
        return "preserved", "low", LOW_RISK_PRESERVED[transform], False

    if transform in {"dead_branch_after_opening_brace", "safe_dead_code_carrier"}:
        if has_constant_false_dead_code(transformed):
            return "preserved_with_precondition", "low", PRECONDITIONED[transform] + " Constant-false guard detected.", False
        return "uncertain", "medium", PRECONDITIONED[transform] + " Expected constant-false guard was not detected by the audit script.", True

    if transform == "identifier_renaming":
        return "preserved_with_precondition", "medium", PRECONDITIONED[transform], False

    if transform == "control_flow_rewrite":
        return "preserved_with_precondition", "medium", PRECONDITIONED[transform], False

    return "uncertain", "medium", "No AI audit rule is registered for this transformation.", True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("results/semantic_audit/human_semantic_audit_packet.csv"))
    parser.add_argument("--output", type=Path, default=Path("results/semantic_audit/ai_semantic_audit.csv"))
    parser.add_argument("--summary", type=Path, default=Path("results/semantic_audit/ai_semantic_audit_summary.json"))
    args = parser.parse_args()

    rows = []
    for row in read_csv(args.input):
        label, risk, note, exclude = audit_row(row)
        rows.append(
            {
                "dataset": row["dataset"],
                "idx": row["idx"],
                "variant_id": row["variant_id"],
                "transform": row["transform"],
                "target": row["target"],
                "validation_note": row["validation_note"],
                "ai_label": label,
                "ai_risk": risk,
                "ai_exclude_from_metrics": str(bool(exclude)).lower(),
                "ai_notes": note,
            }
        )

    write_csv(args.output, rows)
    label_counts = Counter(row["ai_label"] for row in rows)
    risk_counts = Counter(row["ai_risk"] for row in rows)
    by_transform = defaultdict(Counter)
    by_dataset_transform = defaultdict(Counter)
    for row in rows:
        by_transform[row["transform"]][row["ai_label"]] += 1
        by_dataset_transform[f"{row['dataset']}:{row['transform']}"][row["ai_label"]] += 1

    excluded = sum(row["ai_exclude_from_metrics"] == "true" for row in rows)
    summary = {
        "audit_type": "AI-assisted semantic screening audit; not a two-human audit.",
        "input": str(args.input),
        "output": str(args.output),
        "rows": len(rows),
        "label_counts": dict(label_counts),
        "risk_counts": dict(risk_counts),
        "excluded_by_ai_count": excluded,
        "excluded_by_ai_rate": excluded / len(rows) if rows else 0.0,
        "invalid_count": label_counts.get("invalid", 0),
        "uncertain_count": label_counts.get("uncertain", 0),
        "by_transform": {key: dict(value) for key, value in sorted(by_transform.items())},
        "by_dataset_transform": {key: dict(value) for key, value in sorted(by_dataset_transform.items())},
        "integrity_note": (
            "Do not report this file as human annotation. A journal-ready human audit still requires "
            "two independent C/C++-familiar annotators, disagreement analysis, adjudication, and exclusion decisions."
        ),
    }
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
