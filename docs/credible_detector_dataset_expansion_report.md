# Credible Detector and Dataset Expansion Report

## Scope

This expansion adds the requested detector set and two additional datasets for
the paper "Robustness of Learning-Based Vulnerability Detectors under
Semantics-Preserving Code Transformations."

## Datasets Conducted Locally

| Dataset | Local raw file | Normalized rows | Secure | Vulnerable | Projects | CWE labels | Median chars |
|---|---:|---:|---:|---:|---:|---:|---:|
| Big-Vul | `data/raw/bigvul.jsonl` | 3,000 | 2,899 | 101 | 180 | 70 | 404 |
| DiverseVul | `data/raw/diversevul.jsonl` | 5,000 | 4,743 | 257 | 521 | 358 | 510 |

The samples were prepared from local Hugging Face parquet downloads after the
dataset rows API hit rate limits. The local summaries are:

- `data/processed/bigvul_summary.json`
- `data/processed/diversevul_summary.json`

## Transformation Generation Conducted Locally

| Dataset | Original rows | Transformed rows | Total rows | Notes |
|---|---:|---:|---:|---|
| Big-Vul | 3,000 | 12,000 | 15,000 | Four transformations applied to each original record. |
| DiverseVul | 5,000 | 20,000 | 25,000 | Four transformations applied to each original record. |

Transformation summaries:

- `data/processed/bigvul_transform_summary.json`
- `data/processed/diversevul_transform_summary.json`

## Stronger Transformation Suite Added

Four stronger semantics-preserving transformation families were added to the
implementation:

- `identifier_renaming`: renames one simple repeated local identifier or
  parameter outside comments and string/character literals.
- `control_flow_rewrite`: inverts a simple returning `if`/`else` pair.
- `safe_dead_code_carrier`: inserts a compile-time-unreachable carrier block.
- `code_normalization_abstraction`: parenthesizes simple return expressions.

Expanded transformed files:

| Dataset | Original rows | Transformed rows | Total rows | Transformations |
|---|---:|---:|---:|---:|
| CodeXGLUE/Devign test | 2,732 | 21,856 | 24,588 | 8 |
| Big-Vul test sample | 3,000 | 24,000 | 27,000 | 8 |
| DiverseVul test sample | 5,000 | 40,000 | 45,000 | 8 |

Expanded summaries:

- `data/processed/codexglue_test_expanded_transform_summary.json`
- `data/processed/bigvul_expanded_transform_summary.json`
- `data/processed/diversevul_expanded_transform_summary.json`

## Credible Detectors Added

| Detector | Family | Status |
|---|---|---|
| LineVul | Transformer line-level detector | Added to manuscript/config; requires local checkpoint or external repo execution. |
| VulBERTa | RoBERTa vulnerability detector | Optional runner added; smoke inference attempted. `transformers`, `safetensors`, and `libclang` were installed for Python 3.11, but model/tokenizer loading did not complete within the low-compute smoke window. |
| CodeBERT fine-tuned on Devign | CodeBERT sequence classifier | Optional runner added; searched public checkpoint was inaccessible/unauthenticated at execution time. Use local fine-tuning or a verified public checkpoint before reporting results. |
| ReVeal | Graph-based detector | Added to manuscript/config as moderate-compute structural baseline. |
| ReGVD | Graph neural detector | Added to manuscript/config as graph neural baseline. |

## New Artifact Files

- `configs/credible_expansion.yaml`
- `scripts/prepare_robustness_datasets.py`
- `scripts/run_hf_vulnerability_detectors.py`
- `data/raw/bigvul.jsonl`
- `data/raw/diversevul.jsonl`
- `data/processed/bigvul_transformed.jsonl`
- `data/processed/diversevul_transformed.jsonl`

## Submission Readiness Assessment

This completes the dataset side of the requested expansion and adds credible
detector execution hooks, but it does not yet complete the credible-detector
results. The paper must not claim final robustness evidence for LineVul,
VulBERTa, CodeBERT-Devign, ReVeal, or ReGVD until their prediction files are
generated and analyzed.

Minimum next gate for an IST-ready result section:

1. Run VulBERTa or CodeBERT-Devign on CodeXGLUE, Big-Vul, and DiverseVul.
2. Run LineVul or ReGVD on at least CodeXGLUE and Big-Vul.
3. Recompute robustness metrics from the credible detector prediction files.
4. Replace pilot-only result tables with credible-detector result tables.
