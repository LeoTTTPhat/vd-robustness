# Robust VD Article Artifact

This artifact contains the article package for the study:

**Robustness of Learning-Based Vulnerability Detectors under
Semantics-Preserving Code Transformations**

## Contents

- `configs/`: study configuration.
- `scripts/`: data preparation, transformation, validation, detector, and
  analysis scripts.
- `results/codexglue/`: validation, prediction, robustness, statistical,
  and aggregation outputs for the lightweight replay sample.
- `data_sample/`: small samples from the normalized and transformed
  CodeXGLUE/Devign files.
- `paper/`: current TeX manuscript and compiled PDF.
- `requirements-public.txt`: pinned Python package set for public-checkpoint
  replay.
- `results/calibration_invariant_robustness*.{csv,json}`: threshold-integrated
  flip rate and rank-displacement robustness summaries used in the article.
- `results/counterfactual_patch_pair_probe*.{csv,json}`: exploratory Big-Vul
  before/after patch-pair ordering and sparse CWE diagnostics for exact public
  VulBERTa, LineVul, and ReGVD checkpoints, with supporting local-family rows.
- `results/juliet_sard_counterfactual_patch_pair_probe*.{csv,json}`:
  Juliet/SARD C bad/good function-pair VDCP summaries for exact public
  VulBERTa, LineVul, and ReGVD checkpoints.
- `results/consistency_cure_6000/`: clean F1, TIFR, and VDCP before/after the
  transformation-consistency training probe.

## Reproduction

From the project root:

```bash
python3 scripts/prepare_codexglue.py
python3 scripts/apply_transforms.py \
  --input data/raw/codexglue_test.jsonl \
  --output data/processed/codexglue_test_transformed.jsonl
python3 scripts/validate_transforms.py \
  --input data/processed/codexglue_test_transformed.jsonl \
  --output results/codexglue/phase4_transform_validation.json
python3 scripts/run_lightweight_detectors.py
python3 scripts/analyze_predictions.py \
  --predictions results/codexglue/token_nb_predictions.jsonl \
    results/codexglue/char4_nb_predictions.jsonl \
    results/codexglue/hash_lr_predictions.jsonl \
  --output results/codexglue/pilot_analysis.json
```

If the full public-checkpoint prediction files are present in the main
repository layout, regenerate the calibration-invariant metrics with:

```bash
python3 scripts/calibration_invariant_robustness.py --root .
```

Regenerate the counterfactual patch-pair probe with:

```bash
python3 scripts/counterfactual_patch_pair_probe.py --root .
```

## Scope

The main repository contains the full article package, including exact public
checkpoint summaries and construct-validity diagnostics. This `artifact/`
directory keeps a compact copy of the manuscript, small sample data, and
lightweight replay workflow for reviewers who want a quick local check before
running larger public-checkpoint inference.
