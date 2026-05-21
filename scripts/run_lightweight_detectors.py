#!/usr/bin/env python3
"""Train low-compute learning-based detectors and predict transformed variants."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re

import numpy as np


TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+|==|!=|<=|>=|->|&&|\|\||[{}()[\];,.*&+\-/<>=%!]")


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def token_features(code: str, max_chars: int) -> list[str]:
    return TOKEN_RE.findall(code[:max_chars])


def char_ngrams(code: str, max_chars: int, n: int = 4) -> list[str]:
    text = re.sub(r"\s+", " ", code[:max_chars])
    if len(text) < n:
        return [text]
    return [text[i : i + n] for i in range(len(text) - n + 1)]


def f1_at_threshold(scores: list[float], labels: list[int], threshold: float) -> float:
    tp = fp = fn = 0
    for score, label in zip(scores, labels):
        pred = int(score >= threshold)
        if pred == 1 and label == 1:
            tp += 1
        elif pred == 1 and label == 0:
            fp += 1
        elif pred == 0 and label == 1:
            fn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def tune_threshold(scores: list[float], labels: list[int]) -> tuple[float, float]:
    unique = sorted(set(scores))
    if len(unique) > 200:
        candidates = np.quantile(np.array(scores), np.linspace(0.02, 0.98, 197)).tolist()
    else:
        candidates = unique
    candidates.extend([min(scores) - 1e-6, max(scores) + 1e-6, 0.0])
    best_t = 0.0
    best_f1 = -1.0
    for threshold in candidates:
        f1 = f1_at_threshold(scores, labels, float(threshold))
        if f1 > best_f1:
            best_f1 = f1
            best_t = float(threshold)
    return best_t, best_f1


class MultinomialNB:
    def __init__(self, feature_fn, max_features: int, alpha: float = 1.0):
        self.feature_fn = feature_fn
        self.max_features = max_features
        self.alpha = alpha

    def fit(self, rows: list[dict], max_chars: int):
        df = Counter()
        class_counts = Counter()
        per_class = {0: Counter(), 1: Counter()}
        token_totals = Counter()
        for row in rows:
            y = int(row["target"])
            feats = self.feature_fn(row["func"], max_chars)
            class_counts[y] += 1
            df.update(set(feats))
            per_class[y].update(feats)
        self.vocab = {feat: i for i, (feat, _) in enumerate(df.most_common(self.max_features))}
        vocab_set = set(self.vocab)
        per_class = {c: Counter({k: v for k, v in cnt.items() if k in vocab_set}) for c, cnt in per_class.items()}
        token_totals = {c: sum(cnt.values()) for c, cnt in per_class.items()}
        v = len(self.vocab)
        self.log_prior = {
            c: math.log((class_counts[c] + self.alpha) / (len(rows) + 2 * self.alpha))
            for c in (0, 1)
        }
        self.log_prob = {}
        for c in (0, 1):
            denom = token_totals[c] + self.alpha * v
            self.log_prob[c] = {
                feat: math.log((per_class[c][feat] + self.alpha) / denom)
                for feat in self.vocab
            }
            self.unk_log_prob = getattr(self, "unk_log_prob", {})
            self.unk_log_prob[c] = math.log(self.alpha / denom)
        return self

    def score_one(self, code: str, max_chars: int) -> float:
        counts = Counter(feat for feat in self.feature_fn(code, max_chars) if feat in self.vocab)
        scores = {0: self.log_prior[0], 1: self.log_prior[1]}
        for c in (0, 1):
            scores[c] += sum(n * self.log_prob[c].get(feat, self.unk_log_prob[c]) for feat, n in counts.items())
        return scores[1] - scores[0]


class HashedLogisticRegression:
    def __init__(self, dim: int = 2**15, epochs: int = 4, lr: float = 0.08, l2: float = 1e-6):
        self.dim = dim
        self.epochs = epochs
        self.lr = lr
        self.l2 = l2

    def _indices(self, code: str, max_chars: int) -> Counter:
        counts = Counter()
        tokens = token_features(code, max_chars)
        for feat in tokens:
            h = int(hashlib.blake2b(feat.encode("utf-8", "ignore"), digest_size=8).hexdigest(), 16)
            counts[h % self.dim] += 1.0
        return counts

    def fit(self, rows: list[dict], max_chars: int):
        self.w = np.zeros(self.dim, dtype=np.float32)
        self.b = 0.0
        pos = sum(int(r["target"]) for r in rows)
        neg = len(rows) - pos
        pos_weight = neg / pos if pos else 1.0
        for _ in range(self.epochs):
            for row in rows:
                y = int(row["target"])
                feats = self._indices(row["func"], max_chars)
                z = self.b + sum(self.w[i] * math.log1p(c) for i, c in feats.items())
                p = 1.0 / (1.0 + math.exp(-max(min(z, 30), -30)))
                weight = pos_weight if y == 1 else 1.0
                grad = weight * (p - y)
                for i, c in feats.items():
                    self.w[i] -= self.lr * (grad * math.log1p(c) + self.l2 * self.w[i])
                self.b -= self.lr * grad
        return self

    def score_one(self, code: str, max_chars: int) -> float:
        feats = self._indices(code, max_chars)
        z = self.b + sum(self.w[i] * math.log1p(c) for i, c in feats.items())
        return float(z)


def load_rows(path: Path) -> list[dict]:
    return list(read_jsonl(path))


def predict_file(model, threshold: float, input_path: Path, output_path: Path, max_chars: int) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with input_path.open("r", encoding="utf-8") as src, output_path.open("w", encoding="utf-8") as out:
        for line in src:
            if not line.strip():
                continue
            row = json.loads(line)
            score = model.score_one(row["func"], max_chars)
            pred = int(score >= threshold)
            out_row = {
                "idx": row["idx"],
                "variant_id": row.get("variant_id", f"{row['idx']}__original"),
                "transform": row.get("transform", "original"),
                "target": int(row["target"]),
                "score": score,
                "pred": pred,
            }
            out.write(json.dumps(out_row) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", type=Path, default=Path("data/raw/codexglue_train.jsonl"))
    parser.add_argument("--validation", type=Path, default=Path("data/raw/codexglue_validation.jsonl"))
    parser.add_argument("--predict", type=Path, default=Path("data/processed/codexglue_test_transformed.jsonl"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/codexglue"))
    parser.add_argument("--max-chars", type=int, default=8000)
    args = parser.parse_args()

    train_rows = load_rows(args.train)
    val_rows = load_rows(args.validation)

    models = {
        "token_nb": MultinomialNB(token_features, max_features=12000),
        "char4_nb": MultinomialNB(char_ngrams, max_features=16000),
        "hash_lr": HashedLogisticRegression(),
    }

    metadata = {"max_chars": args.max_chars, "models": {}}
    for name, model in models.items():
        print(f"Training {name}...")
        model.fit(train_rows, args.max_chars)
        val_scores = [model.score_one(row["func"], args.max_chars) for row in val_rows]
        val_labels = [int(row["target"]) for row in val_rows]
        threshold, val_f1 = tune_threshold(val_scores, val_labels)
        output_path = args.output_dir / f"{name}_predictions.jsonl"
        predict_file(model, threshold, args.predict, output_path, args.max_chars)
        metadata["models"][name] = {
            "threshold": threshold,
            "validation_f1_at_threshold": val_f1,
            "prediction_file": str(output_path),
        }
        print(f"{name}: threshold={threshold:.6f} validation_f1={val_f1:.4f} -> {output_path}")

    metadata_path = args.output_dir / "lightweight_detector_metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

