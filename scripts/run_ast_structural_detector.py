#!/usr/bin/env python3
"""Train and run a lightweight AST-structural vulnerability detector.

This detector is intentionally local and low-compute. It is not a public
Devign/ReVeal checkpoint. Its purpose is to add a non-collapsed structural
baseline whose features come from tree-sitter C AST shape and node-type counts
rather than token sequence models.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import f1_score
from sklearn.preprocessing import StandardScaler
from tree_sitter import Language, Parser
import tree_sitter_c


NODE_TYPES = [
    "function_definition",
    "compound_statement",
    "if_statement",
    "for_statement",
    "while_statement",
    "switch_statement",
    "case_statement",
    "return_statement",
    "call_expression",
    "assignment_expression",
    "binary_expression",
    "unary_expression",
    "pointer_expression",
    "subscript_expression",
    "field_expression",
    "declaration",
    "init_declarator",
    "parameter_declaration",
    "preproc_if",
    "preproc_call",
    "comment",
]


def make_parser() -> Parser:
    parser = Parser()
    parser.language = Language(tree_sitter_c.language())
    return parser


PARSER = make_parser()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def ast_features(code: str) -> list[float]:
    tree = PARSER.parse(code.encode("utf-8", errors="ignore"))
    counts: Counter[str] = Counter()
    max_depth = 0
    leaf_count = 0
    error_nodes = 0
    named_nodes = 0
    stack = [(tree.root_node, 0)]
    while stack:
        node, depth = stack.pop()
        if node.is_named:
            named_nodes += 1
            counts[node.type] += 1
            max_depth = max(max_depth, depth)
            if node.type in ("ERROR", "MISSING") or node.has_error:
                error_nodes += 1
        if node.child_count == 0:
            leaf_count += 1
        for child in node.children:
            stack.append((child, depth + 1))
    features = [
        named_nodes,
        leaf_count,
        max_depth,
        error_nodes,
        error_nodes / named_nodes if named_nodes else 0.0,
        tree.root_node.child_count,
        len(code),
        code.count("{"),
        code.count(";"),
        code.count("->") + code.count("."),
    ]
    features.extend(float(counts[t]) for t in NODE_TYPES)
    total = sum(counts.values()) or 1
    features.extend(float(counts[t] / total) for t in NODE_TYPES)
    return features


def tune_threshold(scores: np.ndarray, labels: np.ndarray) -> tuple[float, float]:
    candidates = np.unique(np.concatenate([np.quantile(scores, np.linspace(0.01, 0.99, 99)), np.array([0.5])]))
    best_t = float(candidates[0])
    best = -1.0
    for threshold in candidates:
        value = f1_score(labels, (scores >= threshold).astype(int), zero_division=0)
        if value > best:
            best = float(value)
            best_t = float(threshold)
    return best_t, best


def write_predictions(rows: list[dict], scores: np.ndarray, threshold: float, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for row, score in zip(rows, scores):
            handle.write(
                json.dumps(
                    {
                        "idx": row["idx"],
                        "variant_id": row.get("variant_id", f"{row['idx']}__original"),
                        "transform": row.get("transform", "original"),
                        "target": int(row["target"]),
                        "score": float(score),
                        "pred": int(score >= threshold),
                        "model_id": "ast_structural_rf_local",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", type=Path, default=Path("data/raw/codexglue_train.jsonl"))
    parser.add_argument("--validation", type=Path, default=Path("data/raw/codexglue_validation.jsonl"))
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--n-estimators", type=int, default=260)
    parser.add_argument("--max-depth", type=int, default=18)
    args = parser.parse_args()

    train_rows = read_jsonl(args.train)
    val_rows = read_jsonl(args.validation)
    test_rows = read_jsonl(args.input)

    x_train = np.array([ast_features(row["func"]) for row in train_rows], dtype=np.float32)
    y_train = np.array([int(row["target"]) for row in train_rows], dtype=np.int64)
    x_val = np.array([ast_features(row["func"]) for row in val_rows], dtype=np.float32)
    y_val = np.array([int(row["target"]) for row in val_rows], dtype=np.int64)
    x_test = np.array([ast_features(row["func"]) for row in test_rows], dtype=np.float32)

    scaler = StandardScaler()
    x_train = scaler.fit_transform(x_train)
    x_val = scaler.transform(x_val)
    x_test = scaler.transform(x_test)
    model = RandomForestClassifier(
        n_estimators=args.n_estimators,
        max_depth=args.max_depth,
        min_samples_leaf=3,
        class_weight="balanced_subsample",
        n_jobs=-1,
        random_state=20260518,
    )
    model.fit(x_train, y_train)
    val_scores = model.predict_proba(x_val)[:, 1]
    threshold, val_f1 = tune_threshold(val_scores, y_val)
    test_scores = model.predict_proba(x_test)[:, 1]
    write_predictions(test_rows, test_scores, threshold, args.output)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(
            {
                "detector": "AST-structural-RF-local",
                "scope_note": "Local non-collapsed structural baseline using tree-sitter C AST node-type and shape features; not a public Devign/ReVeal checkpoint.",
                "train": str(args.train),
                "validation": str(args.validation),
                "input": str(args.input),
                "output": str(args.output),
                "validation_f1": val_f1,
                "threshold": threshold,
                "feature_count": int(x_train.shape[1]),
                "train_n": len(train_rows),
                "validation_n": len(val_rows),
                "test_rows": len(test_rows),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"output": str(args.output), "threshold": threshold, "validation_f1": val_f1, "rows": len(test_rows)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
