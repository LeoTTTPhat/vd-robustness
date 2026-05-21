# Robust VD Pilot Artifact

This artifact contains the low-compute pilot package for the study:

**Robustness of Learning-Based Vulnerability Detectors under
Semantics-Preserving Code Transformations**

## Contents

- `configs/`: frozen study configuration.
- `scripts/`: data preparation, transformation, validation, detector, and
  analysis scripts.
- `results/codexglue/`: pilot validation, prediction, robustness, statistical,
  and aggregation outputs.
- `data_sample/`: small samples from the normalized and transformed
  CodeXGLUE/Devign files.
- `paper/`: current TeX manuscript and compiled PDF.

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

## Scope

This is a pilot artifact. It validates the workflow using three local
lightweight detectors. The final IST-scale evaluation should add stronger
transformer and graph-based detectors, complete the manual audit sheet, and
replicate results on a secondary dataset such as Big-Vul.

