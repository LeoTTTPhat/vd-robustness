# Phase 4-10 Execution Report

## Phase 4: Transformation Validation

Status: completed for automated pilot checks.

Generated files:

- `results/codexglue/phase4_transform_validation.json`
- `results/codexglue/manual_audit_sheet.csv`

Automated findings:

- All transformed rows preserve the original label.
- All transformed rows are non-empty.
- All transformed rows contain an opening brace.
- Brace-balance rate is 0.975 for every transformation, matching the original
  extracted snippets. This indicates that unbalanced snippets are a dataset
  extraction issue, not a transformation-specific issue.

Manual audit:

- A 120-row audit sheet was generated.
- It contains 30 changed samples per transformation.
- Manual syntax/semantic review is still required before final submission.

## Phase 5: Detector Execution

Status: completed for low-compute pilot detectors.

Detector configurations:

| Detector | Description | Max chars | Threshold selection |
|---|---|---:|---|
| Token-NB | Token multinomial Naive Bayes | 8,000 | Validation F1 |
| Char4-NB | Character 4-gram multinomial Naive Bayes | 8,000 | Validation F1 |
| Hash-LR | Hashed lexical logistic regression | 8,000 | Validation F1 |

Generated predictions:

- `results/codexglue/token_nb_predictions.jsonl`
- `results/codexglue/char4_nb_predictions.jsonl`
- `results/codexglue/hash_lr_predictions.jsonl`
- `results/codexglue/lightweight_detector_metadata.json`

## Phase 6: Robustness Metrics

Status: completed.

Generated files:

- `results/codexglue/token_nb_robustness.json`
- `results/codexglue/char4_nb_robustness.json`
- `results/codexglue/hash_lr_robustness.json`
- `results/codexglue/pilot_analysis.json`

Pilot summary:

| Detector | Clean P | Clean R | Clean F1 | Flip rate | Robust recall | Complete resistance |
|---|---:|---:|---:|---:|---:|---:|
| Token-NB | 0.473 | 0.948 | 0.631 | 0.00156 | 0.944 | 0.996 |
| Char4-NB | 0.459 | 1.000 | 0.630 | 0.00000 | 1.000 | 1.000 |
| Hash-LR | 0.459 | 1.000 | 0.630 | 0.00027 | 0.999 | 0.999 |

## Phase 7: Statistical Summaries

Status: completed in `pilot_analysis.json`.

Implemented:

- Bootstrap confidence intervals for F1 drops.
- Bootstrap confidence intervals for recall drops.
- McNemar paired discordance summaries.

Largest observed recall drop:

- Token-NB under comment insertion: recall drop 0.004, bootstrap 95% CI
  [0.001, 0.008].
- Token-NB under dead-branch insertion: recall drop 0.002, bootstrap 95% CI
  [0.000, 0.005].

## Phase 8: Aggregation Mitigation

Status: completed.

Strategies:

- Original only.
- Majority vote.
- Mean score.
- Max-risk.

Pilot finding:

- Majority vote and max-risk do not change the pilot results because
  predictions are already very stable.
- Mean-score aggregation increases precision but sharply reduces recall.

## Phase 9: TeX Update

Status: completed.

Updated:

- `paper/main.tex`
- `paper/main.pdf`

Added:

- Pilot detector descriptions.
- Dataset and variant-generation results.
- Transformation validation results.
- RQ1-RQ4 pilot tables.
- Bootstrap and McNemar summary text.

## Phase 10: Artifact Package

Status: completed.

Generated:

- `artifact/`

The artifact contains scripts, configuration, result files, paper files, and
small data samples.

## Important Limitation

The current results are a low-compute pilot. Two detectors predict nearly all
test samples as vulnerable, which gives high recall and low precision. This is
useful for validating the pipeline but not enough for a final IST submission.
The final paper should add stronger transformer and graph-based detectors and
complete the manual audit.

