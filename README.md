# vd-robustness

Artifact package for the article:

**Robustness of Learning-Based Vulnerability Detectors under Semantics-Preserving Code Transformations**

This repository supports a Journal of Systems and Software submission on
transformation-based verification and validation of learning-based vulnerability
detection tools. The study asks whether a detector preserves its prediction
when source code is changed in ways that should preserve program behavior and
vulnerability status.

The contribution is not a new vulnerability detector. It is a reproducible
protocol, transformed benchmark package, prediction archive, and analysis suite
for measuring detector robustness under harmless source-level changes.

## What Is Included

- Conservative source-code transformations for function-level vulnerability
  benchmarks.
- Transformed CodeXGLUE/Devign, Big-Vul, and DiverseVul samples.
- Exact public detector outputs for full transformed CodeXGLUE where feasible.
- Supporting local detector-family baselines and structural diagnostics.
- Human semantic-audit materials and summaries.
- Statistical robustness analyses, confidence intervals, paired tests, and
  aggregation diagnostics.
- Calibration-invariant robustness metrics, including threshold-integrated
  flip rate (TIFR) and rank-displacement robustness.
- Counterfactual Big-Vul before/after patch-pair ordering metrics for exact
  public VulBERTa, LineVul, and ReGVD, including vulnerability dominance
  counterfactual-pair (VDCP) and sparse CWE diagnostics.
- Juliet/SARD C patch-pair extraction and exact-public VDCP results over 400
  construction-guaranteed bad/good pairs.
- A low-compute transformation-consistency training probe reporting clean F1,
  TIFR, and VDCP before/after the cure.
- The LaTeX manuscript, figures, references, compiled PDF, and JSS highlights.

## Main Empirical Scope

The primary detector-specific evidence is CodeXGLUE/Devign:

- 2,732 original CodeXGLUE test functions.
- 21,856 transformed variants.
- Exact public VulBERTa and LineVul checkpoint inference.
- Official ReGVD graph implementation on the full transformed test set.
- Public GraphCodeBERT-Devign checkpoint on a stratified 512-origin subset.
- Full-test AST-structural ExtraTrees baseline and subset AST-structural RF
  baseline as non-collapsed local structural evidence.

Big-Vul and DiverseVul are used as external-validity probes for transformation
applicability and imbalance-aware reporting, not as full cross-dataset detector
rankings.
The Big-Vul before/after fix pairs are additionally used for an exploratory
counterfactual patch-pair probe with exact public VulBERTa, LineVul, and
validation-calibrated ReGVD; these results diagnose vulnerability-specific score
ordering but remain limited by the 101 available Big-Vul patch pairs.
Juliet/SARD C bad/good function pairs add a larger synthetic counterfactual
probe: 400 pairs across 47 CWEs, evaluated with the same exact-public detector
trio.

## Repository Structure

```text
configs/
  study.yaml                         Main study configuration.
  credible_expansion.yaml            Detector/dataset expansion notes.

data/
  raw/                               Prepared benchmark inputs.
  processed/                         Transformed datasets and summaries.
  public_exact_slices/               512-origin and smaller exact-checkpoint slices.

docs/
  study_protocol.md                  Empirical protocol.
  human_semantic_audit_protocol.md   Human audit instructions.
  phase_*_report.md                  Execution notes from earlier phases.

paper/
  main.tex                           JSS-oriented manuscript.
  main.pdf                           Compiled manuscript.
  highlights_jss.txt                 Elsevier/JSS highlights.
  figures/                           TikZ figures used in the article.
  references.bib                     Bibliography.

results/
  public_exact/                      Exact public checkpoint summaries.
  public_checkpoints/                Public checkpoint execution status.
  credible_local/                    Supporting local detector-family results.
  semantic_audit/                    Audit packets and summaries.
  codexglue/                         Earlier lightweight/pilot outputs.

scripts/
  apply_transforms.py                Apply transformations to JSONL functions.
  prepare_robustness_datasets.py     Prepare expanded transformed datasets.
  run_hf_vulnerability_detectors.py  Run Hugging Face detector checkpoints.
  run_regvd_scored_inference.py      Run scored ReGVD inference.
  summarize_exact_public_results.py  Summarize exact public predictions.
  analyze_exact_public_enhanced.py   Enhanced analyses and mechanism checks.
  calibration_invariant_robustness.py TIFR and rank-robustness analysis.
  counterfactual_patch_pair_probe.py Big-Vul and Juliet/SARD patch-pair ordering.
  prepare_juliet_sard_pairs.py       Extract bounded Juliet/SARD C bad/good pairs.
  consistency_cure_probe.py          Transformation-consistency training probe.
  statistical_robustness_analysis.py Statistical tests and confidence intervals.

src/src/robust_vd/
  transformations.py                 Transformation implementations.
```

## Data Format

Input benchmark rows use JSONL records with at least:

```json
{"idx": 1, "func": "int f() { return 0; }", "target": 0}
```

Prediction rows use JSONL records with at least:

```json
{"idx": 1, "variant_id": "1__comment_banner", "target": 0, "score": 0.12, "pred": 0}
```

`idx` links an original function to all transformed variants. `variant_id`
identifies the transformation instance.

## Minimal Smoke Workflow

Generate transformed variants:

```bash
python3 scripts/apply_transforms.py \
  --input data/raw/smoke.jsonl \
  --output data/processed/smoke_transformed.jsonl
```

Compute robustness from prediction rows:

```bash
python3 scripts/compute_robustness.py \
  --predictions results/smoke_predictions.jsonl \
  --output results/smoke_robustness_summary.json
```

These commands are intended as lightweight checks of the transformation and
metric pipeline. Full public-checkpoint inference requires the model
dependencies and checkpoints described below.

## Environment

For public-checkpoint replay, use Python 3.12 and the pinned package set in
`requirements-public.txt`:

```bash
python3.12 -m venv .venv_torch
.venv_torch/bin/pip install -r requirements-public.txt
```

The original runs converted public `.bin` weights to `safetensors` where the
installed Transformers/PyTorch stack blocked unsafe binary loading. The
prediction files and execution manifest under `results/public_checkpoints/`
record those conversions and the exact input/output paths.

## Exact Public Detector Runs

The article uses exact public detector inference where possible. Example
commands:

```bash
HF_HUB_DISABLE_XET=1 .venv_torch/bin/python scripts/run_hf_vulnerability_detectors.py \
  --model vulberta_devign_public \
  --input data/processed/codexglue_test_expanded_transformed.jsonl \
  --output results/public_exact/vulberta_mlp_devign/codexglue_full_predictions.jsonl \
  --batch-size 32 \
  --device auto
```

```bash
HF_HUB_DISABLE_XET=1 .venv_torch/bin/python scripts/run_hf_vulnerability_detectors.py \
  --model linevul_public \
  --input data/processed/codexglue_test_expanded_transformed.jsonl \
  --output results/public_exact/linevul_mickymike/codexglue_full_predictions.jsonl \
  --batch-size 32 \
  --device auto
```

ReGVD execution uses the cloned official implementation under
`external/GNN-ReGVD/` and the wrapper:

```bash
.venv_torch/bin/python scripts/run_regvd_scored_inference.py --help
```

The completed summaries are already included under `results/public_exact/` and
`results/public_checkpoints/`.

## Reproducing Article Tables

Useful summary files:

- `results/public_exact/exact_public_codexglue_full_summary.csv`
- `results/public_exact/exact_public_codexglue_full_by_transform.csv`
- `results/public_exact/exact_public_enhanced_analysis.json`
- `results/public_exact/exact_public_flip_logistic_regression.csv`
- `results/public_exact/exact_public_enhanced_aggregation.csv`
- `results/calibration_invariant_robustness.csv`
- `results/calibration_invariant_robustness_summary.json`
- `results/counterfactual_patch_pair_probe.csv`
- `results/counterfactual_patch_pair_probe_summary.json`
- `results/counterfactual_patch_pair_probe_cwe.csv`
- `results/juliet_sard_counterfactual_patch_pair_probe_summary.json`
- `results/consistency_cure_6000/consistency_cure_summary.json`
- `results/semantic_audit/human_semantic_audit_packet.summary.json`
- `results/credible_local/credible_local_summary.csv`
- `results/credible_local/statistical_robustness_summary.csv`

Regenerate the calibration-invariant robustness metrics:

```bash
python3 scripts/calibration_invariant_robustness.py --root .
```

Regenerate the Big-Vul counterfactual patch-pair probe:

```bash
python3 scripts/counterfactual_patch_pair_probe.py --root .
```

Regenerate the Juliet/SARD pair sample and counterfactual summary after
downloading Juliet v1.3 into `data/sources/juliet_sard/`:

```bash
python3 scripts/prepare_juliet_sard_pairs.py --max-pairs 400 --per-cwe 12
python3 scripts/counterfactual_patch_pair_probe.py --root . \
  --metadata data/raw/juliet_sard_pairs.jsonl \
  --output results/juliet_sard_counterfactual_patch_pair_probe.csv \
  --summary results/juliet_sard_counterfactual_patch_pair_probe_summary.json \
  --cwe-output results/juliet_sard_counterfactual_patch_pair_probe_cwe.csv \
  --prediction VulBERTa-public=results/public_exact/vulberta_mlp_devign/juliet_sard_pairs_original_predictions.jsonl \
  --prediction LineVul-public=results/public_exact/linevul_mickymike/juliet_sard_pairs_original_predictions.jsonl \
  --prediction ReGVD-official-validation-calibrated=results/public_exact/regvd_codexglue_full_regrun/juliet_sard_pairs_original_scored_predictions.jsonl
```

Rebuild the manuscript PDF:

```bash
cd paper
latexmk -pdf -interaction=nonstopmode main.tex
```

## Semantic Audit

The audit materials are in `docs/` and `results/semantic_audit/`.

The completed audit covers 864 audit units. No invalid transformations were
found in the audited sampling frame; 11 conservative uncertain cases were
excluded. The article reports a 95% upper bound of 0.43% on the invalid rate
under the stated sampling assumptions.

## Important Interpretation Notes

- CodeXGLUE/Devign is the primary empirical basis for detector-specific claims.
- Big-Vul and DiverseVul are external-validity probes, not full primary
  detector-evaluation datasets.
- LineVul and ReGVD results are strongly affected by operating-point
  calibration and should be interpreted together with recall, predicted-positive
  rate, balanced accuracy, MCC, PR-AUC, TIFR, and rank stability.
- The main full-test results evaluate single transformations. Composition
  probes are supporting diagnostics.
- LLM-based vulnerability detectors are outside the empirical scope of this
  artifact because their prompt format, sampling controls, model versions, and
  costs require a different paired-evaluation design.

## Citation

If you use this artifact, please cite the associated article once available.
Until then, cite the repository:

```bibtex
@misc{trantruong2026vdrobustness,
  title = {vd-robustness: Robustness of Learning-Based Vulnerability Detectors under Semantics-Preserving Code Transformations},
  author = {Tran-Truong, Phat T. and Le, Xuan-Bach},
  year = {2026},
  howpublished = {\url{https://github.com/LeoTTTPhat/vd-robustness}}
}
```

## Repository

Project URL:

```text
https://github.com/LeoTTTPhat/vd-robustness
```
