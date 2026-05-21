# Data Preparation

This directory stores local study data.

## Primary Dataset

The primary dataset is CodeXGLUE/Devign defect detection. It is normalized to
JSONL with the following schema:

```json
{"idx": 1, "func": "int f() { return 0; }", "target": 0}
```

Run:

```bash
python3 scripts/prepare_codexglue.py
```

Then generate transformed variants for the test split:

```bash
python3 scripts/apply_transforms.py \
  --input data/raw/codexglue_test.jsonl \
  --output data/processed/codexglue_test_transformed.jsonl
```

Summarize generated variants:

```bash
python3 scripts/summarize_transforms.py \
  --input data/processed/codexglue_test_transformed.jsonl \
  --output data/processed/codexglue_test_transform_summary.json
```

## Detector Aging / Model Drift Data

The temporal detector-aging pipeline expects JSONL records with date-bearing
metadata:

```json
{
  "idx": "stable id",
  "func": "int f() { return 0; }",
  "target": 0,
  "date": "2020-01-01",
  "project": "project-name",
  "cwe": "CWE-119"
}
```

Run the full Phase 1-9 smoke workflow:

```bash
python3 scripts/conduct_detector_aging.py
```

Run it on a real temporal dataset:

```bash
python3 scripts/conduct_detector_aging.py \
  --input data/raw/cvefixes_functions.jsonl \
  --source-name CVEfixes
```

Prepare the current Hugging Face mirrors through the dataset rows API:

```bash
python3 scripts/prepare_temporal_vuln_datasets.py \
  --dataset cvefixes \
  --via-api \
  --api-sample-step 500 \
  --api-sample-length 10 \
  --max-raw-rows 60
```

The DiverseVul mirror does not expose explicit dates in the visible schema, so
the temporal export uses CVE years recovered from commit messages as proxy
dates. Treat DiverseVul results as a sensitivity check unless explicit commit
dates are enriched separately.

For full Hugging Face parquet downloads, provide `HF_TOKEN` in the environment
and use the authenticated parallel downloader:

```bash
python3 scripts/download_hf_parquet.py --dataset cvefixes
python3 scripts/download_hf_parquet.py --dataset diversevul
```

Full temporal exports produced in the current study:

- `data/raw/cvefixes_full_temporal.jsonl`
- `data/raw/diversevul_full_temporal.jsonl`
