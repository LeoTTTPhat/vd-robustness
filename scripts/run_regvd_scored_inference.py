#!/usr/bin/env python3
"""Run scored inference for the public GNN-ReGVD implementation.

The upstream ReGVD runner writes only hard predictions at a fixed 0.5
threshold. This wrapper keeps the upstream model/dataset code but exports
probabilities and optionally selects a validation-set threshold, which is
needed when the trained checkpoint is calibrated below 0.5.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import f1_score
from torch.utils.data import DataLoader, SequentialSampler


def add_regvd_to_path(repo_root: Path) -> None:
    code_dir = repo_root / "external" / "GNN-ReGVD" / "code"
    sys.path.insert(0, str(code_dir))


def load_upstream(repo_root: Path):
    add_regvd_to_path(repo_root)
    import run as regvd_run  # type: ignore
    from model import DevignModel, GNNReGVD  # type: ignore

    return regvd_run, DevignModel, GNNReGVD


def build_model(args, regvd_run, DevignModel, GNNReGVD):
    config_class, model_class, tokenizer_class = regvd_run.MODEL_CLASSES[args.model_type]
    config = config_class.from_pretrained(args.config_name or args.model_name_or_path)
    config.num_labels = 1
    tokenizer = tokenizer_class.from_pretrained(args.tokenizer_name)
    encoder = model_class.from_pretrained(args.model_name_or_path, config=config)
    if args.model == "devign":
        model = DevignModel(encoder, config, tokenizer, args)
    else:
        model = GNNReGVD(encoder, config, tokenizer, args)
    state = torch.load(args.checkpoint, map_location=args.device)
    model.load_state_dict(state)
    model.to(args.device)
    model.eval()
    return model, tokenizer


def collect_scores(args, regvd_run, model, tokenizer, input_file: Path):
    dataset = regvd_run.TextDataset(tokenizer, args, str(input_file))
    loader = DataLoader(
        dataset,
        sampler=SequentialSampler(dataset),
        batch_size=args.eval_batch_size,
    )
    scores: list[float] = []
    labels: list[int] = []
    with torch.no_grad():
        for batch in loader:
            input_ids = batch[0].to(args.device)
            label = batch[1].cpu().numpy().astype(int).tolist()
            prob = model(input_ids).detach().cpu().numpy()[:, 0]
            scores.extend(float(x) for x in prob)
            labels.extend(label)
    return dataset.examples, np.asarray(labels), np.asarray(scores)


def tune_threshold(labels: np.ndarray, scores: np.ndarray) -> tuple[float, float]:
    candidates = np.unique(scores)
    if len(candidates) > 2000:
        candidates = np.quantile(scores, np.linspace(0.0, 1.0, 2000))
    best_threshold = 0.5
    best_f1 = -1.0
    for threshold in candidates:
        pred = (scores >= threshold).astype(int)
        f1 = f1_score(labels, pred, zero_division=0)
        if f1 > best_f1:
            best_f1 = f1
            best_threshold = float(threshold)
    return best_threshold, float(best_f1)


def metadata_by_id(path: Path) -> dict[str, dict]:
    rows = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            rows[str(row["idx"])] = row
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--eval-data-file", type=Path)
    parser.add_argument("--threshold", default="validation-f1")
    parser.add_argument("--model-type", default="roberta")
    parser.add_argument("--model-name-or-path", required=True)
    parser.add_argument("--tokenizer-name", required=True)
    parser.add_argument("--config-name", default="")
    parser.add_argument("--model", default="GNNs")
    parser.add_argument("--block-size", type=int, default=128)
    parser.add_argument("--eval-batch-size", type=int, default=128)
    parser.add_argument("--hidden-size", type=int, default=64)
    parser.add_argument("--feature-dim-size", type=int, default=768)
    parser.add_argument("--num-GNN-layers", type=int, default=1)
    parser.add_argument("--num-classes", type=int, default=2)
    parser.add_argument("--gnn", default="ReGCN")
    parser.add_argument("--format", default="uni")
    parser.add_argument("--window-size", type=int, default=3)
    parser.add_argument("--remove-residual", action="store_true")
    parser.add_argument("--att-op", default="mul")
    args = parser.parse_args()

    args.repo_root = args.repo_root.resolve()
    args.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    args.n_gpu = torch.cuda.device_count() if torch.cuda.is_available() else 0
    args.per_gpu_eval_batch_size = args.eval_batch_size
    args.local_rank = -1

    regvd_run, DevignModel, GNNReGVD = load_upstream(args.repo_root)
    model, tokenizer = build_model(args, regvd_run, DevignModel, GNNReGVD)

    chosen_threshold = 0.5
    threshold_note = "fixed"
    validation_f1 = None
    if args.threshold == "validation-f1":
        if not args.eval_data_file:
            raise SystemExit("--eval-data-file is required for validation-f1 thresholding")
        _, val_labels, val_scores = collect_scores(args, regvd_run, model, tokenizer, args.eval_data_file)
        chosen_threshold, validation_f1 = tune_threshold(val_labels, val_scores)
        threshold_note = "validation_f1_optimal"
    else:
        chosen_threshold = float(args.threshold)

    examples, labels, scores = collect_scores(args, regvd_run, model, tokenizer, args.input)
    meta = metadata_by_id(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    positives = 0
    with args.output.open("w", encoding="utf-8") as handle:
        for example, label, score in zip(examples, labels, scores):
            variant_id = str(example.idx)
            pred = int(score >= chosen_threshold)
            positives += pred
            source = meta.get(variant_id, {})
            handle.write(
                json.dumps(
                    {
                        "idx": source.get("source_idx", variant_id.split("__", 1)[0]),
                        "variant_id": source.get("variant_id", variant_id),
                        "transform": source.get("transform", "original"),
                        "target": int(label),
                        "score": float(score),
                        "pred": pred,
                    }
                )
                + "\n"
            )

    manifest = {
        "checkpoint": str(args.checkpoint),
        "input": str(args.input),
        "output": str(args.output),
        "threshold": chosen_threshold,
        "threshold_note": threshold_note,
        "validation_f1": validation_f1,
        "rows": int(len(scores)),
        "positive_predictions": int(positives),
        "score_min": float(scores.min()) if len(scores) else None,
        "score_max": float(scores.max()) if len(scores) else None,
        "score_mean": float(scores.mean()) if len(scores) else None,
    }
    manifest_path = args.output.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
