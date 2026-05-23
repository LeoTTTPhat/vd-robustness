#!/usr/bin/env python3
"""Low-compute transformation-consistency cure probe.

This script trains the same hashed logistic detector in two conditions:
original-only training and transformation-consistency training, where
semantics-preserving variants of training functions inherit the original label.
It then reports clean F1, TIFR, and VDCP before/after the cure.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
from bisect import bisect_right
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "src"))

from robust_vd.transformations import apply_all  # noqa: E402


TOKEN_RE = __import__("re").compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+|==|!=|<=|>=|->|&&|\|\||[{}()[\];,.*&+\-/<>=%!]")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]


def token_features(code: str, max_chars: int = 8000) -> Counter[int]:
    counts: Counter[int] = Counter()
    for tok in TOKEN_RE.findall(code[:max_chars]):
        h = hash(tok) % (2**18)
        counts[h] += 1
    return counts


class HashLR:
    def __init__(self, dim: int = 2**18, epochs: int = 4, lr: float = 0.05, l2: float = 1e-6):
        self.dim = dim
        self.epochs = epochs
        self.lr = lr
        self.l2 = l2
        self.w = np.zeros(dim, dtype=np.float32)
        self.b = 0.0

    def fit(self, rows: list[dict]) -> "HashLR":
        pos = sum(int(r["target"]) for r in rows)
        neg = len(rows) - pos
        pos_weight = neg / max(pos, 1)
        rng = random.Random(20260523)
        for _ in range(self.epochs):
            rng.shuffle(rows)
            for row in rows:
                y = int(row["target"])
                feats = token_features(row["func"])
                z = self.b + sum(self.w[i] * math.log1p(c) for i, c in feats.items())
                p = 1.0 / (1.0 + math.exp(-max(min(float(z), 30), -30)))
                weight = pos_weight if y else 1.0
                grad = weight * (p - y)
                for i, c in feats.items():
                    self.w[i] -= self.lr * (grad * math.log1p(c) + self.l2 * self.w[i])
                self.b -= self.lr * grad
        return self

    def score_one(self, code: str) -> float:
        feats = token_features(code)
        return float(self.b + sum(self.w[i] * math.log1p(c) for i, c in feats.items()))


def f1(scores: list[float], labels: list[int], threshold: float) -> float:
    tp = fp = fn = 0
    for s, y in zip(scores, labels):
        p = int(s >= threshold)
        tp += int(p == 1 and y == 1)
        fp += int(p == 1 and y == 0)
        fn += int(p == 0 and y == 1)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    return 2 * prec * rec / (prec + rec) if prec + rec else 0.0


def tune(scores: list[float], labels: list[int]) -> tuple[float, float]:
    candidates = np.quantile(np.array(scores), np.linspace(0.02, 0.98, 193)).tolist()
    candidates.extend([min(scores) - 1e-6, max(scores) + 1e-6, 0.0])
    best_t, best_f = 0.0, -1.0
    for t in candidates:
        value = f1(scores, labels, float(t))
        if value > best_f:
            best_t, best_f = float(t), value
    return best_t, best_f


def predict_rows(model: HashLR, rows: list[dict], threshold: float, output: Path, detector: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for row in rows:
            score = model.score_one(row["func"])
            handle.write(
                json.dumps(
                    {
                        "idx": row["idx"],
                        "variant_id": row.get("variant_id", f"{row['idx']}__original"),
                        "transform": row.get("transform", "original"),
                        "target": int(row["target"]),
                        "score": score,
                        "pred": int(score >= threshold),
                        "model_id": detector,
                    }
                )
                + "\n"
            )


def expand_training(rows: list[dict], max_origins: int) -> list[dict]:
    rng = random.Random(20260523)
    pos = [r for r in rows if int(r["target"]) == 1]
    neg = [r for r in rows if int(r["target"]) == 0]
    each = max_origins // 2
    selected = rng.sample(pos, min(each, len(pos))) + rng.sample(neg, min(max_origins - each, len(neg)))
    augmented: list[dict] = []
    for row in selected:
        augmented.append(row)
        for variant in apply_all(row["func"]):
            if variant.changed:
                augmented.append({"idx": row["idx"], "target": row["target"], "func": variant.code})
    return augmented


def empirical_percentile(sorted_values: list[float], value: float) -> float:
    return bisect_right(sorted_values, value) / len(sorted_values)


def tifr(pred_rows: list[dict]) -> float:
    originals = {str(r["idx"]): r for r in pred_rows if r["transform"] == "original"}
    clean_scores = sorted(float(r["score"]) for r in originals.values())
    displacements = []
    for row in pred_rows:
        if row["transform"] == "original" or str(row["idx"]) not in originals:
            continue
        orig = originals[str(row["idx"])]
        displacements.append(
            abs(empirical_percentile(clean_scores, float(orig["score"])) - empirical_percentile(clean_scores, float(row["score"])))
        )
    return sum(displacements) / len(displacements)


def vdcp(pred_rows: list[dict]) -> float:
    by_pair: dict[str, dict[str, dict]] = defaultdict(dict)
    for row in pred_rows:
        idx = str(row["idx"])
        if idx.endswith("-before"):
            by_pair[idx[: -len("-before")]]["before"] = row
        elif idx.endswith("-after"):
            by_pair[idx[: -len("-after")]]["after"] = row
    successes = []
    for both in by_pair.values():
        if "before" in both and "after" in both:
            successes.append(float(both["before"]["score"]) > float(both["after"]["score"]))
    return sum(successes) / len(successes)


def load_preds(path: Path) -> list[dict]:
    return read_jsonl(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", type=Path, default=Path("data/raw/codexglue_train.jsonl"))
    parser.add_argument("--validation", type=Path, default=Path("data/raw/codexglue_validation.jsonl"))
    parser.add_argument("--codexglue", type=Path, default=Path("data/processed/codexglue_test_expanded_transformed.jsonl"))
    parser.add_argument("--bigvul-pairs", type=Path, default=Path("data/public_exact_slices/bigvul_101_patch_pairs_expanded.jsonl"))
    parser.add_argument("--juliet-pairs", type=Path, default=Path("data/raw/juliet_sard_pairs.jsonl"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/consistency_cure"))
    parser.add_argument("--train-origins", type=int, default=3000)
    args = parser.parse_args()

    train_rows = read_jsonl(args.train)
    val_rows = read_jsonl(args.validation)
    codex_rows = read_jsonl(args.codexglue)
    bigvul_rows = read_jsonl(args.bigvul_pairs)
    juliet_rows = read_jsonl(args.juliet_pairs)

    conditions = {
        "hash_lr_original": train_rows,
        "hash_lr_consistency": expand_training(train_rows, args.train_origins),
    }
    summary: list[dict] = []
    for name, fit_rows in conditions.items():
        model = HashLR().fit(list(fit_rows))
        val_scores = [model.score_one(r["func"]) for r in val_rows]
        val_labels = [int(r["target"]) for r in val_rows]
        threshold, val_f1 = tune(val_scores, val_labels)
        paths = {
            "codexglue": args.output_dir / f"{name}_codexglue_predictions.jsonl",
            "bigvul": args.output_dir / f"{name}_bigvul_patch_predictions.jsonl",
            "juliet": args.output_dir / f"{name}_juliet_sard_predictions.jsonl",
        }
        predict_rows(model, codex_rows, threshold, paths["codexglue"], name)
        predict_rows(model, bigvul_rows, threshold, paths["bigvul"], name)
        predict_rows(model, juliet_rows, threshold, paths["juliet"], name)

        codex_preds = load_preds(paths["codexglue"])
        original_preds = [r for r in codex_preds if r["transform"] == "original"]
        clean_f1 = f1([float(r["score"]) for r in original_preds], [int(r["target"]) for r in original_preds], threshold)
        summary.append(
            {
                "detector": name,
                "train_rows": len(fit_rows),
                "threshold": threshold,
                "validation_f1": val_f1,
                "codexglue_clean_f1": clean_f1,
                "codexglue_tifr": tifr(codex_preds),
                "bigvul_vdcp": vdcp(load_preds(paths["bigvul"])),
                "juliet_sard_vdcp": vdcp(load_preds(paths["juliet"])),
                "codexglue_predictions": str(paths["codexglue"]),
                "bigvul_predictions": str(paths["bigvul"]),
                "juliet_predictions": str(paths["juliet"]),
            }
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary_json = args.output_dir / "consistency_cure_summary.json"
    summary_json.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    with (args.output_dir / "consistency_cure_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary[0].keys()))
        writer.writeheader()
        writer.writerows(summary)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
