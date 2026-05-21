# Study Protocol

## 1. Positioning

This study is an empirical software engineering paper. The software engineering
problem is that vulnerability detectors are increasingly used in code review,
CI/CD, and security triage, but they are usually validated on clean benchmark
functions. A detector that changes its prediction after harmless edits can
mislead developers and weaken automated quality gates.

The paper should therefore be framed around **robustness as a software quality
property of AI-enabled security tools**, not around proposing a bigger
classifier.

## 2. Scope

### In Scope

- Function-level vulnerability detection.
- Source-level C/C++ functions.
- Semantics-preserving or syntax-preserving transformations.
- Binary vulnerable/non-vulnerable prediction.
- Low-compute baselines and reproducible metrics.

### Out of Scope for the First Submission

- Full-program vulnerability exploitation.
- Expensive large-model fine-tuning.
- Whole-repository build validation for every transformed sample.
- Dynamic proof that all transformed snippets are behaviorally equivalent.

## 3. Datasets

### Primary Dataset

**CodeXGLUE/Devign defect detection**

Use this first because it is small enough for quick iteration and widely used
in vulnerability detection. The test split is also convenient for a
transformation-only robustness study.

### Secondary Datasets

**Big-Vul**

Use as a real-world CVE-linked dataset for external validity.

**DiverseVul**

Use for scale and project/CWE diversity after the pipeline is stable.

## 4. Transformation Families

### T1: Lexical Noise

Examples:

- Insert harmless comments.
- Add blank lines.
- Shift brace layout.
- Normalize spacing.

Expected semantic effect: none.

Research value: tests whether detectors over-rely on superficial token layout.

### T2: Dead-Code Carriers

Examples:

- Insert an unreachable `if (0)` block after the opening brace.
- Insert an unused local declaration where valid.

Expected semantic effect: none if inserted inside a valid function body and the
snippet remains syntactically valid.

Research value: tests whether detectors are sensitive to irrelevant token
carriers.

### T3: Identifier Transformations

Examples:

- Rename local variables consistently.
- Abstract variable names by role.

Expected semantic effect: none if scope is respected.

Research value: tests whether models learn vulnerability-relevant structure or
memorize names.

### T4: Control-Flow Normalization

Examples:

- Convert simple `if (cond) return a; return b;` to `return cond ? a : b;`.
- Normalize equivalent loop forms when safe.

Expected semantic effect: none for constrained patterns.

Research value: tests structural robustness.

## 5. Transformation Validation

Use a three-level validation policy.

### Level 1: Syntax Validity

The transformed code must parse or pass a lightweight syntax check.

### Level 2: Conservative Rule Design

Transformations must be implemented only for patterns where preservation is
obvious. If a pattern is ambiguous, skip the sample.

### Level 3: Manual Audit

Randomly inspect at least 30 samples per transformation family. Report the
audit process and invalid transformation rate.

For the IST paper, this validation section is crucial. Recent evidence shows
that many claimed semantics-preserving transformations are actually unsafe when
reused across real code.

## 6. Models

### Low-Compute Baselines

- Frozen CodeBERT/VulBERTa embeddings with logistic regression.
- Existing LineVul checkpoint if available.
- Prompted small code LLM for a sample subset.

### Optional Expanded Baselines

- ReVeal.
- ReGVD or another graph-based model.
- A compact open-weight code model with zero-shot prompting.

## 7. Metrics

### Clean Metrics

- Accuracy.
- Precision.
- Recall.
- F1.
- AUC if scores are available.

### Robustness Metrics

Let `x` be an original function and `T(x)` be its transformed variants.

**Prediction Flip Rate**

Percentage of transformed variants whose prediction differs from the original
prediction.

**Robust Accuracy**

Percentage of original samples for which the clean prediction is correct and all
transformed variants remain correct.

**Robust Recall**

Same as robust accuracy but computed only on vulnerable samples.

**Complete Resistance**

Percentage of originally detected vulnerable samples that remain detected under
all transformation variants.

**Worst-Case F1 Drop**

Clean F1 minus the minimum F1 across transformation families.

## 8. Research Questions and Analysis Plan

### RQ1: Overall Robustness

Compare clean performance to transformed performance by model and dataset.

### RQ2: Transformation Sensitivity

Rank transformation families by prediction flip rate and F1 drop.

### RQ3: Label-Specific Fragility

Compare vulnerable and non-vulnerable samples. The expected concern is that
vulnerable samples may have higher flip rates, reducing security recall.

### RQ4: Low-Cost Mitigation

Evaluate variant aggregation:

- Majority vote over original plus transformed variants.
- Max-risk rule: predict vulnerable if any variant is predicted vulnerable.
- Mean score aggregation if probability scores are available.

## 9. Threats to Validity

### Construct Validity

Some transformations may preserve syntax but not behavior. Mitigate with
conservative rules, syntax checks, and manual audit.

### Internal Validity

Prediction changes may be caused by truncation, tokenization, or preprocessing.
Record token lengths and report truncation rates.

### External Validity

Function-level benchmarks may not represent real CI/CD use. Mitigate with
secondary CVE-linked datasets and a discussion of deployment boundaries.

### Conclusion Validity

Use paired statistical tests and effect sizes because predictions are paired by
original/transformed variants.

## 10. Minimum Publishable Experiment

The smallest IST-ready version should include:

- CodeXGLUE/Devign test split.
- At least 4 conservative transformations.
- At least 3 detector families or configurations.
- Robustness metrics, statistical tests, and manual audit.
- Open artifact with transformed benchmark and scripts.

