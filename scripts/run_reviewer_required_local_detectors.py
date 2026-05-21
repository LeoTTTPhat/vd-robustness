#!/usr/bin/env python3
"""Run reviewer-required detector families with local, bounded implementations.

This script is intentionally explicit about its scope. It produces executed
prediction files for the requested detector *families* when public heavyweight
checkpoints cannot be downloaded in the current workspace:

- codebert_devign_local: Devign-trained lexical sequence classifier.
- vulberta_devign_local: Devign-trained normalized-code classifier.
- linevul_local: line-pooled vulnerability detector.
- regvd_structural_local: ReGVD-inspired structural feature detector.

These are not a substitute for successfully loading the public CodeBERT,
VulBERTa, LineVul, and ReGVD checkpoints; the manuscript must describe them as
local reproduced family baselines unless the checkpoint runs are completed.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import re

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+|==|!=|<=|>=|->|&&|\|\||[{}()[\];,.*&+\-/<>=%!]")
COMMENT_RE = re.compile(r"//.*?$|/\*.*?\*/", re.MULTILINE | re.DOTALL)
STRING_RE = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')
NUMBER_RE = re.compile(r"\b(?:0x[0-9a-fA-F]+|\d+(?:\.\d+)?)\b")
CONTROL_WORDS = ("if", "else", "for", "while", "switch", "case", "return", "goto", "break", "continue")
RISK_WORDS = (
    "strcpy",
    "strncpy",
    "strcat",
    "sprintf",
    "snprintf",
    "gets",
    "memcpy",
    "memmove",
    "malloc",
    "free",
    "delete",
    "new",
    "NULL",
    "null",
    "sizeof",
    "len",
    "length",
    "size",
    "buffer",
    "buf",
    "ptr",
)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def normalize_code(code: str) -> str:
    text = COMMENT_RE.sub(" ", code)
    text = STRING_RE.sub(" STR_LIT ", text)
    text = NUMBER_RE.sub(" NUM_LIT ", text)
    return " ".join(TOKEN_RE.findall(text))


def codebert_text(code: str) -> str:
    return " ".join(TOKEN_RE.findall(code[:8000]))


def max_depth(code: str) -> int:
    depth = best = 0
    for ch in code:
        if ch == "{":
            depth += 1
            best = max(best, depth)
        elif ch == "}":
            depth = max(0, depth - 1)
    return best


def structural_features(code: str) -> list[float]:
    tokens = TOKEN_RE.findall(code[:12000])
    counts = Counter(tokens)
    lines = [line for line in code.splitlines() if line.strip()]
    n_tokens = len(tokens)
    n_lines = len(lines)
    unique = len(set(tokens))
    operators = sum(counts[t] for t in ("==", "!=", "<=", ">=", "&&", "||", "!", "=", "+", "-", "*", "/", "%"))
    calls = len(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\s*\(", code))
    risk = sum(counts[w] for w in RISK_WORDS)
    control = sum(counts[w] for w in CONTROL_WORDS)
    return [
        len(code),
        n_lines,
        n_tokens,
        unique,
        unique / n_tokens if n_tokens else 0.0,
        max_depth(code),
        code.count("{"),
        code.count(";"),
        calls,
        control,
        risk,
        operators,
        counts["if"],
        counts["for"] + counts["while"],
        counts["return"],
        counts["NULL"] + counts["null"],
        counts["malloc"] + counts["free"] + counts["new"] + counts["delete"],
        counts["memcpy"] + counts["strcpy"] + counts["sprintf"] + counts["snprintf"],
        max((len(line) for line in lines), default=0),
        sum(len(line) for line in lines) / n_lines if n_lines else 0.0,
    ]


def f1_at_threshold(scores: np.ndarray, labels: np.ndarray, threshold: float) -> float:
    preds = (scores >= threshold).astype(int)
    tp = int(((preds == 1) & (labels == 1)).sum())
    fp = int(((preds == 1) & (labels == 0)).sum())
    fn = int(((preds == 0) & (labels == 1)).sum())
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return 2 * p * r / (p + r) if p + r else 0.0


def tune_threshold(scores: np.ndarray, labels: np.ndarray) -> tuple[float, float]:
    candidates = np.quantile(scores, np.linspace(0.01, 0.99, 99))
    candidates = np.unique(np.concatenate([candidates, np.array([0.0, 0.5])]))
    best_t = float(candidates[0])
    best_f1 = -1.0
    for threshold in candidates:
        f1 = f1_at_threshold(scores, labels, float(threshold))
        if f1 > best_f1:
            best_t = float(threshold)
            best_f1 = f1
    return best_t, best_f1


class Detector:
    def fit(self, rows: list[dict], val_rows: list[dict]) -> dict:
        raise NotImplementedError

    def score(self, code: str) -> float:
        raise NotImplementedError

    def batch_scores(self, codes: list[str]) -> np.ndarray:
        return np.array([self.score(code) for code in codes], dtype=np.float32)


class TextDetector(Detector):
    def __init__(self, name: str, preprocessor, analyzer: str, ngram_range: tuple[int, int], max_features: int):
        self.name = name
        self.preprocessor = preprocessor
        self.pipeline = Pipeline(
            [
                (
                    "tfidf",
                    TfidfVectorizer(
                        preprocessor=preprocessor,
                        tokenizer=str.split if analyzer == "word" else None,
                        token_pattern=None if analyzer == "word" else r"(?u)\b\w+\b",
                        analyzer=analyzer,
                        ngram_range=ngram_range,
                        max_features=max_features,
                        min_df=2,
                    ),
                ),
                (
                    "clf",
                    LogisticRegression(
                        class_weight="balanced",
                        max_iter=1000,
                        solver="liblinear",
                        random_state=20260517,
                    ),
                ),
            ]
        )

    def fit(self, rows: list[dict], val_rows: list[dict]) -> dict:
        self.pipeline.fit([row["func"] for row in rows], [int(row["target"]) for row in rows])
        val_scores = self.pipeline.predict_proba([row["func"] for row in val_rows])[:, 1]
        labels = np.array([int(row["target"]) for row in val_rows])
        self.threshold, val_f1 = tune_threshold(val_scores, labels)
        return {"threshold": self.threshold, "validation_f1": val_f1}

    def score(self, code: str) -> float:
        return float(self.pipeline.predict_proba([code])[:, 1][0])

    def batch_scores(self, codes: list[str]) -> np.ndarray:
        return self.pipeline.predict_proba(codes)[:, 1]


class LinePooledDetector(TextDetector):
    def score(self, code: str) -> float:
        lines = [line for line in code.splitlines() if line.strip()]
        if not lines:
            return super().score(code)
        # LineVul-style function score: high if any individual line is risky.
        line_scores = self.pipeline.predict_proba(lines)[:, 1]
        return float(max(line_scores))


class StructuralDetector(Detector):
    def fit(self, rows: list[dict], val_rows: list[dict]) -> dict:
        x = np.array([structural_features(row["func"]) for row in rows], dtype=np.float32)
        y = np.array([int(row["target"]) for row in rows], dtype=np.int64)
        self.scaler = StandardScaler()
        x_scaled = self.scaler.fit_transform(x)
        self.model = RandomForestClassifier(
            n_estimators=180,
            max_depth=18,
            min_samples_leaf=3,
            class_weight="balanced_subsample",
            random_state=20260517,
            n_jobs=-1,
        )
        self.model.fit(x_scaled, y)
        val_x = self.scaler.transform(np.array([structural_features(row["func"]) for row in val_rows], dtype=np.float32))
        val_scores = self.model.predict_proba(val_x)[:, 1]
        labels = np.array([int(row["target"]) for row in val_rows])
        self.threshold, val_f1 = tune_threshold(val_scores, labels)
        return {"threshold": self.threshold, "validation_f1": val_f1}

    def score(self, code: str) -> float:
        x = self.scaler.transform(np.array([structural_features(code)], dtype=np.float32))
        return float(self.model.predict_proba(x)[:, 1][0])

    def batch_scores(self, codes: list[str]) -> np.ndarray:
        x = self.scaler.transform(np.array([structural_features(code) for code in codes], dtype=np.float32))
        return self.model.predict_proba(x)[:, 1]


def write_predictions(detector: Detector, input_path: Path, output_path: Path, batch_size: int = 4096) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with input_path.open("r", encoding="utf-8") as src, output_path.open("w", encoding="utf-8") as out:
        batch: list[dict] = []
        seen = 0

        def flush_batch() -> None:
            nonlocal batch, seen
            if not batch:
                return
            scores = detector.batch_scores([row["func"] for row in batch])
            for row, score_value in zip(batch, scores):
                score = float(score_value)
                pred = int(score >= detector.threshold)
                out.write(
                    json.dumps(
                        {
                            "idx": row["idx"],
                            "variant_id": row.get("variant_id", f"{row['idx']}__original"),
                            "transform": row.get("transform", "original"),
                            "target": int(row["target"]),
                            "score": score,
                            "pred": pred,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            seen += len(batch)
            if seen // 10000 != (seen - len(batch)) // 10000:
                print(f"{output_path.name}: predicted {seen}", flush=True)
            batch = []

        for line in src:
            if line.strip():
                batch.append(json.loads(line))
            if len(batch) >= batch_size:
                flush_batch()
        flush_batch()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", type=Path, default=Path("data/raw/codexglue_train.jsonl"))
    parser.add_argument("--validation", type=Path, default=Path("data/raw/codexglue_validation.jsonl"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/credible_local"))
    parser.add_argument("--datasets", nargs="+", required=True, type=Path)
    parser.add_argument("--detectors", nargs="+", default=None, help="Optional detector names to run.")
    args = parser.parse_args()

    train_rows = read_jsonl(args.train)
    val_rows = read_jsonl(args.validation)
    detectors: dict[str, Detector] = {
        "codebert_devign_local": TextDetector("codebert_devign_local", codebert_text, "word", (1, 2), 50000),
        "vulberta_devign_local": TextDetector("vulberta_devign_local", normalize_code, "char", (3, 5), 70000),
        "linevul_local": LinePooledDetector("linevul_local", codebert_text, "word", (1, 2), 50000),
        "regvd_structural_local": StructuralDetector(),
    }

    metadata = {
        "scope_note": (
            "Executed local detector-family reproductions. These are not the public heavyweight "
            "checkpoints unless separately stated."
        ),
        "training_dataset": str(args.train),
        "validation_dataset": str(args.validation),
        "detectors": {},
    }
    if args.detectors:
        unknown = set(args.detectors) - set(detectors)
        if unknown:
            raise SystemExit(f"Unknown detectors: {', '.join(sorted(unknown))}")
        detectors = {name: detectors[name] for name in args.detectors}
    for name, detector in detectors.items():
        print(f"Training {name}", flush=True)
        metadata["detectors"][name] = detector.fit(train_rows, val_rows)
        for dataset_path in args.datasets:
            dataset_name = dataset_path.stem.replace("_expanded_transformed", "").replace("_test", "")
            output_path = args.output_dir / dataset_name / f"{name}_predictions.jsonl"
            print(f"Predicting {name} on {dataset_path}", flush=True)
            write_predictions(detector, dataset_path, output_path)
            metadata["detectors"][name].setdefault("prediction_files", {})[dataset_name] = str(output_path)

    metadata_path = args.output_dir / "credible_local_detector_metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
