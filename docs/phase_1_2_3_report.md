# Phase 1-3 Execution Report

## Phase 1: Study Design Freeze

Status: completed.

Frozen decisions:

- Primary dataset: CodeXGLUE/Devign defect detection.
- Secondary dataset for the next phase: Big-Vul.
- Language scope: C/C++ function-level vulnerability detection.
- Initial transformations:
  - `comment_banner`
  - `blank_line_expansion`
  - `brace_line_shift`
  - `dead_branch_after_opening_brace`
- Minimum detector families for later phases:
  - Frozen code-model embeddings plus lightweight classifier.
  - Existing transformer vulnerability detector checkpoint.
  - Prompted compact/API code model on a subset.

These decisions are recorded in `configs/study.yaml`.

## Phase 2: Dataset Preparation

Status: completed for the primary dataset.

The CodeXGLUE/Devign Hugging Face Parquet splits were downloaded and normalized
to JSONL with the schema:

```json
{"idx": 1, "func": "int f() { return 0; }", "target": 0}
```

Generated files:

- `data/raw/codexglue_train.jsonl`
- `data/raw/codexglue_validation.jsonl`
- `data/raw/codexglue_test.jsonl`
- `data/processed/codexglue_summary.json`

Dataset summary:

| Split | Rows | Secure | Vulnerable | Vulnerable Ratio | Median Chars | Max Chars |
|---|---:|---:|---:|---:|---:|---:|
| Train | 21,854 | 11,836 | 10,018 | 0.458 | 935 | 142,346 |
| Validation | 2,732 | 1,545 | 1,187 | 0.434 | 928 | 137,221 |
| Test | 2,732 | 1,477 | 1,255 | 0.459 | 966 | 142,292 |

## Phase 3: Variant Generation

Status: completed for validation and test splits.

Generated files:

- `data/processed/codexglue_validation_transformed.jsonl`
- `data/processed/codexglue_validation_transform_summary.json`
- `data/processed/codexglue_test_transformed.jsonl`
- `data/processed/codexglue_test_transform_summary.json`

Each original sample is preserved as an `original` variant and receives four
transformed variants.

### Test Split Transformation Summary

| Transform | Rows | Changed | Unchanged | Applicability |
|---|---:|---:|---:|---:|
| `comment_banner` | 2,732 | 2,732 | 0 | 1.000 |
| `dead_branch_after_opening_brace` | 2,732 | 2,732 | 0 | 1.000 |
| `brace_line_shift` | 2,732 | 2,661 | 71 | 0.974 |
| `blank_line_expansion` | 2,732 | 1,864 | 868 | 0.682 |

The transformed test file contains 13,660 total rows:

- 2,732 original rows.
- 10,928 transformed rows.

### Validation Split Transformation Summary

| Transform | Rows | Changed | Unchanged | Applicability |
|---|---:|---:|---:|---:|
| `comment_banner` | 2,732 | 2,732 | 0 | 1.000 |
| `dead_branch_after_opening_brace` | 2,732 | 2,732 | 0 | 1.000 |
| `brace_line_shift` | 2,732 | 2,672 | 60 | 0.978 |
| `blank_line_expansion` | 2,732 | 1,831 | 901 | 0.670 |

The transformed validation file contains 13,660 total rows:

- 2,732 original rows.
- 10,928 transformed rows.

## Reproduction Commands

Prepare CodeXGLUE/Devign:

```bash
python3 scripts/prepare_codexglue.py
```

Generate test variants:

```bash
python3 scripts/apply_transforms.py \
  --input data/raw/codexglue_test.jsonl \
  --output data/processed/codexglue_test_transformed.jsonl
```

Summarize test variants:

```bash
python3 scripts/summarize_transforms.py \
  --input data/processed/codexglue_test_transformed.jsonl \
  --output data/processed/codexglue_test_transform_summary.json
```

## Verification

The preparation and transformation scripts compile successfully:

```bash
python3 -m py_compile \
  scripts/prepare_codexglue.py \
  scripts/apply_transforms.py \
  scripts/summarize_transforms.py \
  src/robust_vd/transformations.py
```

## Next Phase

Phase 4 should validate transformation correctness:

- Add syntax/parser checks for transformed C/C++ snippets.
- Generate a manual audit sheet with 30 samples per transformation.
- Record invalid or suspicious variants before detector inference.

