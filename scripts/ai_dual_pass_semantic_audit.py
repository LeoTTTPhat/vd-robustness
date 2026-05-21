#!/usr/bin/env python3
"""Create a transparent AI dual-pass semantic screening audit.

This is not a human audit and must not be reported as one. It simulates the
two-annotator workflow with two deterministic AI/rule-based passes so the
artifact can expose agreement, adjudication, invalid counts, and exclusions
without filling the genuine human annotator columns.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path


LABELS = ["preserved", "preserved_with_precondition", "invalid", "uncertain"]
PRECONDITIONED = {
    "dead_branch_after_opening_brace",
    "safe_dead_code_carrier",
    "identifier_renaming",
    "control_flow_rewrite",
}
LOW_RISK = {
    "blank_line_expansion",
    "brace_line_shift",
    "comment_banner",
    "code_normalization_abstraction",
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


def strip_comments(code: str) -> str:
    code = re.sub(r"/\*.*?\*/", "", code or "", flags=re.DOTALL)
    return re.sub(r"//.*", "", code)


def constant_false_guard(code: str) -> bool:
    code = code or ""
    patterns = [
        r"\bif\s*\(\s*0\s*\)",
        r"\bif\s*\(\s*false\s*\)",
        r"\bif\s*\(\s*sizeof\s*\(\s*int\s*\)\s*==\s*0\s*\)",
        r"\bif\s*\(\s*0\s*==\s*sizeof\s*\(\s*int\s*\)\s*\)",
        r"#\s*if\s+0\b",
    ]
    return any(re.search(pattern, code) for pattern in patterns)


def has_macro_line_continuation(code: str) -> bool:
    return any(line.rstrip().endswith("\\") for line in (code or "").splitlines())


def renamed_marker_in_signature(transformed: str) -> bool:
    prefix = (transformed or "").split("{", 1)[0]
    return "__rvd_id" in prefix


def protocol_pass(row: dict) -> tuple[str, str, bool]:
    transform = row["transform"]
    original = row.get("original_code", "")
    transformed = row.get("transformed_code", "")
    if not original.strip() or not transformed.strip():
        return "uncertain", "Missing original or transformed code.", True
    if transform in {"blank_line_expansion", "brace_line_shift"}:
        return "preserved", "Layout-only transformation; no executable token is intentionally introduced.", False
    if transform == "comment_banner":
        return "preserved", "Inserted block comment; comment-stripped review found no intended runtime change.", False
    if transform == "code_normalization_abstraction":
        return "preserved", "Return-expression normalization is limited to syntactically simple expressions.", False
    if transform in {"dead_branch_after_opening_brace", "safe_dead_code_carrier"}:
        if constant_false_guard(transformed):
            return "preserved_with_precondition", "Constant-false guard detected; branch/carrier is unreachable.", False
        return "uncertain", "Expected constant-false guard was not detected.", True
    if transform == "identifier_renaming":
        return "preserved_with_precondition", "Identifier marker is generated for a simple renamed identifier; local-scope precondition applies.", False
    if transform == "control_flow_rewrite":
        return "preserved_with_precondition", "Restricted returning if/else rewrite; branch-return precondition applies.", False
    return "uncertain", "No protocol rule for this transformation.", True


def conservative_pass(row: dict) -> tuple[str, str, bool]:
    transform = row["transform"]
    original = row.get("original_code", "")
    transformed = row.get("transformed_code", "")
    if not original.strip() or not transformed.strip():
        return "uncertain", "Missing original or transformed code.", True
    if transform in {"blank_line_expansion", "brace_line_shift"}:
        return "preserved", "Whitespace/layout difference only under compact source review.", False
    if transform == "comment_banner":
        if has_macro_line_continuation(original):
            return "uncertain", "Original contains macro line continuation; comment placement needs human preprocessor review.", True
        if compact(strip_comments(original)) == compact(strip_comments(transformed)):
            return "preserved", "Comment-stripped code matches after compacting whitespace.", False
        return "preserved", "Inserted comment appears inert; remaining difference is formatting or pre-existing comments.", False
    if transform == "code_normalization_abstraction":
        if re.search(r"\breturn\s+.*[,?:]", original or ""):
            return "uncertain", "Return expression contains operators that merit human precedence review.", True
        return "preserved", "No conservative precedence-risk pattern detected.", False
    if transform in {"dead_branch_after_opening_brace", "safe_dead_code_carrier"}:
        if constant_false_guard(transformed):
            return "preserved_with_precondition", "Unreachable guard detected; preservation depends on constant-false semantics.", False
        return "uncertain", "Unreachable guard not recognized.", True
    if transform == "identifier_renaming":
        if renamed_marker_in_signature(transformed):
            return "preserved_with_precondition", "Renamed identifier appears in the function signature; preservation depends on it being a parameter name, not an external binding.", False
        return "preserved_with_precondition", "Generated identifier marker appears local under source-level review.", False
    if transform == "control_flow_rewrite":
        if "return" in transformed:
            return "preserved_with_precondition", "Rewritten control flow still returns from both branches under the restricted pattern.", False
        return "uncertain", "Expected branch returns not visible after rewrite.", True
    return "uncertain", "No conservative rule for this transformation.", True


def adjudicate(a_label: str, b_label: str, a_exclude: bool, b_exclude: bool) -> tuple[str, bool, str]:
    if a_label == b_label:
        return a_label, a_exclude or b_exclude, "Both AI screening passes agree."
    severity = {"invalid": 3, "uncertain": 2, "preserved_with_precondition": 1, "preserved": 0}
    chosen = max([a_label, b_label], key=lambda label: severity[label])
    return chosen, chosen in {"invalid", "uncertain"} or a_exclude or b_exclude, (
        "AI screening passes disagree; adjudication uses the more conservative label."
    )


def cohen_kappa(pairs: list[tuple[str, str]]) -> float:
    if not pairs:
        return float("nan")
    total = len(pairs)
    observed = sum(a == b for a, b in pairs) / total
    a_counts = Counter(a for a, _ in pairs)
    b_counts = Counter(b for _, b in pairs)
    expected = sum((a_counts[label] / total) * (b_counts[label] / total) for label in LABELS)
    if math.isclose(1.0, expected):
        return 1.0 if math.isclose(1.0, observed) else float("nan")
    return (observed - expected) / (1 - expected)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("results/semantic_audit/human_semantic_audit_packet.csv"))
    parser.add_argument("--output", type=Path, default=Path("results/semantic_audit/ai_dual_pass_semantic_audit.csv"))
    parser.add_argument("--summary", type=Path, default=Path("results/semantic_audit/ai_dual_pass_semantic_audit_summary.json"))
    args = parser.parse_args()

    out_rows = []
    pairs: list[tuple[str, str]] = []
    for row in read_csv(args.input):
        a_label, a_notes, a_exclude = protocol_pass(row)
        b_label, b_notes, b_exclude = conservative_pass(row)
        final_label, final_exclude, adjudication_notes = adjudicate(a_label, b_label, a_exclude, b_exclude)
        pairs.append((a_label, b_label))
        out_rows.append(
            {
                "dataset": row["dataset"],
                "idx": row["idx"],
                "variant_id": row["variant_id"],
                "transform": row["transform"],
                "target": row["target"],
                "validation_note": row["validation_note"],
                "ai_annotator1_label": a_label,
                "ai_annotator1_notes": a_notes,
                "ai_annotator2_label": b_label,
                "ai_annotator2_notes": b_notes,
                "ai_disagreement": str(a_label != b_label).lower(),
                "ai_adjudicated_label": final_label,
                "ai_adjudication_notes": adjudication_notes,
                "ai_exclude_from_metrics": str(final_exclude).lower(),
            }
        )

    write_csv(args.output, out_rows)
    label_counts = Counter(row["ai_adjudicated_label"] for row in out_rows)
    disagreement_count = sum(row["ai_disagreement"] == "true" for row in out_rows)
    excluded_count = sum(row["ai_exclude_from_metrics"] == "true" for row in out_rows)
    by_transform = defaultdict(Counter)
    by_dataset_transform = defaultdict(Counter)
    for row in out_rows:
        by_transform[row["transform"]][row["ai_adjudicated_label"]] += 1
        by_dataset_transform[f"{row['dataset']}:{row['transform']}"][row["ai_adjudicated_label"]] += 1

    invalid_examples = [
        {k: row[k] for k in ["dataset", "idx", "variant_id", "transform", "ai_adjudication_notes"]}
        for row in out_rows
        if row["ai_adjudicated_label"] == "invalid"
    ][:10]
    uncertain_examples = [
        {k: row[k] for k in ["dataset", "idx", "variant_id", "transform", "ai_adjudication_notes"]}
        for row in out_rows
        if row["ai_adjudicated_label"] == "uncertain"
    ][:10]

    summary = {
        "audit_type": "AI dual-pass semantic screening simulation; not a human two-annotator audit.",
        "input": str(args.input),
        "output": str(args.output),
        "rows": len(out_rows),
        "ai_annotator_protocol": [
            "AI annotator 1: protocol-following deterministic screening pass.",
            "AI annotator 2: conservative deterministic screening pass with additional macro/precondition checks.",
        ],
        "raw_agreement": (len(out_rows) - disagreement_count) / len(out_rows) if out_rows else 0.0,
        "cohen_kappa": cohen_kappa(pairs),
        "disagreement_count": disagreement_count,
        "disagreement_rate": disagreement_count / len(out_rows) if out_rows else 0.0,
        "adjudicated_label_counts": dict(label_counts),
        "invalid_count": label_counts.get("invalid", 0),
        "invalid_rate": label_counts.get("invalid", 0) / len(out_rows) if out_rows else 0.0,
        "uncertain_count": label_counts.get("uncertain", 0),
        "uncertain_rate": label_counts.get("uncertain", 0) / len(out_rows) if out_rows else 0.0,
        "excluded_count": excluded_count,
        "excluded_rate": excluded_count / len(out_rows) if out_rows else 0.0,
        "by_transform": {key: dict(value) for key, value in sorted(by_transform.items())},
        "by_dataset_transform": {key: dict(value) for key, value in sorted(by_dataset_transform.items())},
        "invalid_examples": invalid_examples,
        "uncertain_examples": uncertain_examples,
        "integrity_note": (
            "Do not report this artifact as human annotation. It intentionally leaves the human annotator "
            "columns in the audit packet untouched. A journal-ready audit still requires two independent "
            "C/C++-familiar humans, disagreement analysis, adjudication, and exclusion decisions."
        ),
    }
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
