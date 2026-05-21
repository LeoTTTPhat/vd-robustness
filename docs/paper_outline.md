# Paper Outline

## Working Title

**Robustness of Learning-Based Vulnerability Detectors under
Semantics-Preserving Code Transformations**

Alternative titles:

- **Beyond Clean Accuracy: Evaluating Vulnerability Detectors under
  Semantics-Preserving Code Transformations**
- **Are Vulnerability Detectors Stable under Harmless Code Edits? A
  Transformation-Based Empirical Study**
- **Robustness as a Software Quality Property for Learning-Based Vulnerability
  Detection**

Recommended title: use the first one. It is direct, clear, and strongly aligned
with empirical software engineering.

## Target Journal Fit

Information and Software Technology is a good target if the paper is framed as
an empirical software engineering contribution rather than a machine learning
model paper.

The manuscript should emphasize:

- Software quality and reliability of AI-enabled security tools.
- Testing and validation of vulnerability detection tools.
- Reproducible empirical method.
- Practical implications for code review, CI/CD, and security triage.

Avoid framing the paper as:

- A new vulnerability detector.
- A pure adversarial machine learning attack paper.
- A benchmark leaderboard paper.

## Core Thesis

Clean benchmark accuracy is an incomplete indicator of practical usefulness for
learning-based vulnerability detectors. If a detector changes its decision after
a harmless code edit, then developers and CI/CD systems cannot safely interpret
its output as a stable software quality signal. Robustness under
semantics-preserving transformations should therefore be measured and reported
as a standard evaluation dimension.

## One-Sentence Contribution

We propose and evaluate a low-compute, transformation-based robustness protocol
for learning-based vulnerability detectors, showing how detector predictions
change under behavior-preserving code edits and how lightweight aggregation can
partially mitigate prediction instability.

## Abstract Draft

Learning-based vulnerability detectors are increasingly used to support
security review and software quality assurance. However, most detectors are
evaluated on clean benchmark functions, while real code evolves through
formatting changes, refactorings, identifier changes, and other edits that
should preserve behavior. This paper presents an empirical study of detector
robustness under semantics-preserving code transformations. We construct a
transformed benchmark from widely used vulnerability detection datasets, define
a detector-agnostic robustness metric suite, and evaluate representative
learning-based detectors under multiple transformation families. Our study
quantifies prediction instability, identifies the transformations that most
degrade security recall, and evaluates low-cost mitigation strategies based on
variant aggregation. The results provide practical guidance for evaluating and
deploying AI-enabled vulnerability detection tools in software engineering
workflows.

Replace the final sentence after experiments with the strongest result, for
example:

> Across three detector families, harmless transformations reduced vulnerable
> recall by X-Y percentage points and caused prediction flips in Z% of
> originally detected vulnerable functions.

## Paper Storyline

The paper should tell a simple story:

1. Vulnerability detectors are moving into software engineering workflows.
2. Current evaluation overemphasizes clean benchmark scores.
3. Real code changes through harmless edits.
4. A useful detector should be stable under those edits.
5. We build a validated transformation benchmark and metric suite.
6. We show where detectors are fragile.
7. We give concrete recommendations for researchers and tool builders.

## Research Questions

### RQ1: Overall Robustness

**How much does detector performance change under semantics-preserving code
transformations?**

Purpose: establish the main empirical phenomenon.

Primary metrics:

- Clean F1 vs transformed F1.
- Clean recall vs transformed recall.
- Robust accuracy.
- Robust recall.

Expected result narrative:

> All evaluated detectors experience measurable degradation under at least one
> transformation family, showing that clean benchmark performance overestimates
> deployment stability.

### RQ2: Transformation Sensitivity

**Which transformation families cause the largest prediction instability?**

Purpose: identify concrete failure modes.

Primary metrics:

- Prediction flip rate by transformation.
- Worst-case F1 drop by transformation.
- Complete resistance by transformation family.

Expected result narrative:

> Structural or carrier-based transformations cause larger instability than
> simple formatting changes, suggesting that detectors rely on brittle lexical
> and syntactic cues.

### RQ3: Label-Specific Fragility

**Are vulnerable functions more fragile than non-vulnerable functions under
equivalent transformations?**

Purpose: connect robustness to security risk.

Primary metrics:

- Flip rate for vulnerable samples.
- Flip rate for non-vulnerable samples.
- Vulnerability recall drop.
- False-negative increase.

Expected result narrative:

> Prediction instability is especially concerning when it converts true
> positives into false negatives, because this weakens CI/CD security gates.

### RQ4: Low-Cost Mitigation

**Can prediction aggregation over transformed variants improve robustness
without retraining detectors?**

Purpose: provide an actionable engineering recommendation.

Aggregation strategies:

- Majority vote over original and transformed variants.
- Max-risk rule: predict vulnerable if any variant is vulnerable.
- Mean score aggregation when scores are available.

Expected result narrative:

> Variant aggregation improves robust recall but may increase false positives,
> creating a tunable tradeoff for security-sensitive workflows.

## Section-by-Section Plan

## 1. Introduction

### Goal

Convince the reader that robustness under harmless code edits is a practical
software engineering requirement for vulnerability detectors.

### Opening Argument

Start from the workflow:

- Developers use automated detectors in pull requests, CI/CD, and security
  audits.
- These tools increasingly include learning-based models.
- A detector may appear accurate on benchmark data but still be unstable under
  edits that preserve behavior.
- Instability matters because code naturally changes through formatting,
  refactoring, identifier changes, and dead-code-preserving edits.

### Concrete Motivating Example

Include a small C/C++ function and one transformed variant.

Example structure:

```c
int read_first(char *p) {
    return p[0];
}
```

Transformed:

```c
int read_first(char *p)
{
    /* robustness_probe: no semantic effect */
    if (0) { int __dead = 0; (void)__dead; }
    return p[0];
}
```

Then state:

> A detector that flags the first version but misses the second is not robust
> to harmless edits.

Do not claim a specific detector result in this example until the experiment
actually produces one.

### Gap

Existing vulnerability detection evaluations usually report clean accuracy,
precision, recall, F1, or AUC. These metrics are necessary but insufficient
because they do not test prediction invariance under behavior-preserving edits.

### Contributions

Use four contributions:

1. **Protocol:** A transformation-based robustness protocol for
   learning-based vulnerability detection.
2. **Benchmark:** A transformed benchmark built from widely used vulnerability
   detection datasets and validated through conservative transformation rules
   and manual audit.
3. **Evidence:** An empirical comparison of detector robustness across
   transformation families, labels, and model families.
4. **Mitigation:** A low-cost evaluation of transformed-variant aggregation as
   a robustness improvement strategy.

### Figure

**Figure 1: Overview of the study pipeline**

Flow:

Original benchmark functions -> transformations -> validation -> detector
inference -> robustness metrics -> mitigation analysis.

## 2. Background and Related Work

### Goal

Show that the paper is grounded in existing software vulnerability detection
and robustness research while identifying a specific empirical gap.

### 2.1 Learning-Based Vulnerability Detection

Cover:

- Sequence/token models.
- Transformer-based code models.
- Graph-based models.
- Line-level and function-level detection.

Writing angle:

> These techniques improve automated detection, but their evaluation often
> focuses on clean benchmark performance.

### 2.2 Vulnerability Detection Benchmarks

Cover:

- CodeXGLUE/Devign.
- Big-Vul.
- DiverseVul.
- Optional: ReVeal, Juliet, D2A depending on final experiment.

Writing angle:

> Public datasets make comparison possible, but clean splits do not measure
> stability under common code edits.

### 2.3 Code Transformations and Metamorphic Testing

Cover:

- Metamorphic testing principle: expected output should remain invariant under
  valid input transformations.
- Semantics-preserving transformations in code intelligence.
- Risk that claimed transformations may accidentally change semantics.

Writing angle:

> This study treats transformations as a test oracle for detector stability,
> while explicitly validating transformation safety.

### 2.4 Robustness of Code Intelligence Models

Cover:

- Robustness of code models under formatting, renaming, normalization, and
  structural changes.
- Recent evidence that code intelligence models can be sensitive to
  semantics-preserving edits.

Writing angle:

> Prior work establishes that code models can be brittle; our study focuses on
> vulnerability detection as a software quality assurance workflow and provides
> detector-oriented robustness metrics and mitigations.

### 2.5 Adversarial Evasion in Security Tools

Cover:

- Adversarial examples for malware, phishing, IDS, and vulnerability detection.
- Distinguish this paper from offensive evasion:
  - Our primary goal is tool validation.
  - Transformations are used as controlled robustness probes.

### Table

**Table 1: Related work comparison**

Columns:

- Study.
- Task.
- Transformations.
- Datasets.
- Models.
- Validates transformation safety?
- Provides detector-agnostic robustness metrics?
- Evaluates mitigation?

## 3. Study Design

### Goal

Define the empirical protocol clearly enough that reviewers trust the results.

### 3.1 Research Questions

List RQ1-RQ4 exactly as above.

### 3.2 Dataset Selection

Primary:

- CodeXGLUE/Devign.

Secondary:

- Big-Vul.
- DiverseVul.

Selection criteria:

- Public availability.
- Prior use in vulnerability detection.
- Function-level code.
- Feasible low-compute evaluation.
- Support for cross-dataset replication.

### 3.3 Transformation Taxonomy

Use four families:

1. Lexical/layout transformations.
2. Comment transformations.
3. Dead-code carrier transformations.
4. Identifier/control-flow transformations.

For first submission, keep the implemented set conservative:

- Comment insertion.
- Blank-line expansion.
- Brace layout shift.
- Unreachable branch insertion.

Expanded set, if time allows:

- Scope-aware identifier renaming.
- Simple conditional normalization.
- Simple loop normalization.

### Table

**Table 2: Transformation taxonomy**

Columns:

- ID.
- Transformation.
- Family.
- Example.
- Expected semantic effect.
- Applicability condition.
- Validation method.

### 3.4 Transformation Validation

Explain three levels:

- Conservative rule design.
- Syntax/parsing check.
- Manual audit.

Manual audit recommendation:

- 30 samples per transformation per dataset.
- Two reviewers if possible.
- Report disagreement and invalid transformation rate.

### 3.5 Detector Selection

Low-compute detector families:

- Frozen code-model embeddings plus logistic regression.
- Existing transformer vulnerability detector checkpoint.
- Prompted small code LLM or API-based LLM on a subset.

Expanded detector families:

- Graph-based detector.
- Line-level detector.

Selection criteria:

- Represents a distinct model family.
- Public implementation/checkpoint available.
- Feasible to run under the compute budget.

### 3.6 Metrics

Clean metrics:

- Accuracy.
- Precision.
- Recall.
- F1.
- AUC when scores are available.

Robustness metrics:

- Prediction flip rate.
- Robust accuracy.
- Robust recall.
- Complete resistance.
- Transformation sensitivity.
- Worst-case F1 drop.

### 3.7 Statistical Analysis

Use paired analysis because each original sample has transformed variants.

Recommended tests:

- McNemar's test for paired prediction differences.
- Bootstrap confidence intervals for F1/recall drops.
- Cliff's delta or odds ratios for effect sizes.

Keep statistics simple and transparent.

## 4. Experimental Setup

### Goal

Make the paper reproducible and reviewer-friendly.

### 4.1 Hardware and Compute Budget

Report:

- CPU model.
- RAM.
- GPU, if used.
- Total runtime per dataset/model.

Low-compute claim:

> All transformations and metric computations run on CPU. Model inference can
> be performed with existing checkpoints; training is limited to lightweight
> classifiers unless otherwise stated.

### 4.2 Data Preparation

Steps:

1. Download benchmark splits.
2. Normalize records to `{idx, func, target}`.
3. Deduplicate if necessary.
4. Sample balanced subsets for pilot runs.
5. Preserve original labels for transformed variants.

### 4.3 Transformation Implementation

Explain:

- Each transformation is deterministic.
- A transformed variant keeps the original label.
- Samples are skipped only when transformation preconditions fail.
- Each variant is linked to its original sample by `idx`.

### 4.4 Detector Execution

Report:

- Tokenizer and maximum length.
- Truncation policy.
- Threshold selection.
- Whether thresholds are fixed from validation data.
- Whether transformed variants are excluded from training.

Important rule:

> Transformations are applied only at evaluation time unless explicitly testing
> mitigation through aggregation. No model sees transformed test variants during
> training.

### 4.5 Reproducibility Package

Release:

- Transformation scripts.
- Configuration files.
- Transformed benchmark metadata.
- Prediction files.
- Metric scripts.
- Manual audit sheet.

### Table

**Table 3: Experimental setup**

Columns:

- Dataset.
- Samples.
- Vulnerable ratio.
- Transformations.
- Variants generated.
- Detector families.
- Hardware/runtime.

## 5. Results

### Goal

Answer each RQ directly. Each subsection should begin with a one-sentence
answer, then provide evidence.

### 5.1 RQ1: Overall Robustness

Start with:

> Answer to RQ1: [fill after experiment].

Include:

- Clean vs transformed metrics table.
- Robust accuracy and robust recall.
- Confidence intervals.

Table:

**Table 4: Clean and transformed performance by detector**

Columns:

- Detector.
- Clean precision.
- Clean recall.
- Clean F1.
- Worst transformed F1.
- F1 drop.
- Robust accuracy.
- Robust recall.

Figure:

**Figure 2: Clean vs transformed F1/recall**

### 5.2 RQ2: Transformation Sensitivity

Start with:

> Answer to RQ2: [fill after experiment].

Include:

- Flip rate by transformation.
- Rank transformations from least to most disruptive.

Table:

**Table 5: Transformation sensitivity**

Columns:

- Transformation.
- Applicable samples.
- Flip rate.
- Vulnerable flip rate.
- Non-vulnerable flip rate.
- F1 drop.

Figure:

**Figure 3: Prediction flip rate by transformation family**

### 5.3 RQ3: Label-Specific Fragility

Start with:

> Answer to RQ3: [fill after experiment].

Include:

- False-negative increase.
- False-positive increase.
- Vulnerable vs non-vulnerable paired comparison.

Table:

**Table 6: Label-specific prediction instability**

Columns:

- Detector.
- Vulnerable flip rate.
- Non-vulnerable flip rate.
- True-positive-to-false-negative rate.
- True-negative-to-false-positive rate.

### 5.4 RQ4: Mitigation through Variant Aggregation

Start with:

> Answer to RQ4: [fill after experiment].

Compare:

- Original-only prediction.
- Majority vote.
- Mean score.
- Max-risk rule.

Table:

**Table 7: Aggregation mitigation results**

Columns:

- Detector.
- Aggregation strategy.
- Precision.
- Recall.
- F1.
- Robust recall.
- False-positive change.

Figure:

**Figure 4: Precision-recall tradeoff of aggregation strategies**

## 6. Discussion

### Goal

Translate results into software engineering implications.

### 6.1 Clean Accuracy Is Not Enough

Argument:

- Clean metrics do not reveal prediction instability.
- Robustness metrics should accompany standard benchmark metrics.

### 6.2 Implications for CI/CD Security Gates

Argument:

- False negatives after harmless edits are more dangerous than ordinary
  instability.
- Security-sensitive workflows may prefer max-risk aggregation despite higher
  false positives.

### 6.3 Implications for Benchmark Designers

Recommendations:

- Include transformed variants in benchmark releases.
- Report transformation validity.
- Separate robustness test sets from training data.
- Track truncation and tokenization artifacts.

### 6.4 Implications for Tool Builders

Recommendations:

- Use robustness tests before deployment.
- Calibrate thresholds under transformed variants.
- Consider variant aggregation.
- Monitor prediction instability across code review revisions.

### 6.5 Why Detectors May Be Brittle

Possible explanations:

- Token-level shortcut learning.
- Identifier memorization.
- Sensitivity to truncation.
- Overfitting to benchmark formatting.
- Weak modeling of data/control dependencies.

## 7. Threats to Validity

### Construct Validity

Risk:

- Transformations may not preserve semantics.

Mitigation:

- Conservative transformations.
- Parsing/syntax checks.
- Manual audit.
- Report invalid transformation rate.

### Internal Validity

Risk:

- Prediction changes may come from preprocessing, tokenization, or truncation
  rather than semantic brittleness.

Mitigation:

- Log token lengths.
- Report truncation rates.
- Use fixed thresholds.
- Keep transformations out of training data.

### External Validity

Risk:

- Function-level datasets may not represent whole-project vulnerability
  detection.

Mitigation:

- Use multiple datasets.
- Discuss deployment boundaries.
- Avoid claiming whole-program equivalence.

### Conclusion Validity

Risk:

- Observed drops may be sample-specific.

Mitigation:

- Paired tests.
- Bootstrap confidence intervals.
- Multiple detector families.
- Release artifacts.

## 8. Conclusion

Main points:

- Learning-based vulnerability detectors should be evaluated not only by clean
  accuracy but also by robustness under harmless code edits.
- The paper provides a low-compute protocol and metric suite.
- The empirical results show which transformations destabilize predictions and
  which mitigations help.
- Robustness under semantics-preserving transformations should become a
  standard part of vulnerability detector evaluation.

## Tables and Figures Checklist

Tables:

1. Related work comparison.
2. Transformation taxonomy.
3. Experimental setup.
4. Clean vs transformed performance.
5. Transformation sensitivity.
6. Label-specific instability.
7. Aggregation mitigation.

Figures:

1. Study pipeline.
2. Clean vs transformed F1/recall.
3. Flip rate by transformation.
4. Aggregation precision-recall tradeoff.
5. Optional heatmap: detector vs transformation sensitivity.

## Minimal IST Submission Package

The first submission should include:

- At least one primary dataset: CodeXGLUE/Devign.
- Preferably one secondary dataset: Big-Vul or DiverseVul.
- At least four validated transformations.
- At least three detector configurations or families.
- Manual transformation audit.
- Complete robustness metric suite.
- Artifact package with scripts, configs, predictions, and transformed metadata.

## Writing Order

Recommended writing order:

1. Study Design.
2. Experimental Setup.
3. Metrics.
4. Related Work.
5. Introduction.
6. Results.
7. Discussion.
8. Threats to Validity.
9. Abstract and Conclusion.

This order avoids over-promising before results exist.

