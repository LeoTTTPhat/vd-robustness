# Reviewer Report (Round 3) — Information and Software Technology (Elsevier)

**Manuscript:** *Robustness of Learning-Based Vulnerability Detectors under Semantics-Preserving Code Transformations*
**Reviewer recommendation:** **Accept with Minor Edits**
**Confidence:** High (familiar with code-intelligence robustness, vulnerability detection benchmarks, and metamorphic testing literature).

---

## 1. Summary of Revision

The authors have addressed essentially all major concerns from round 2. The paper now includes:

- **Predicted-positive columns** (`Clean pred.+`, `Var. pred.+`) in Table 4, making the near-all-positive nature of the calibrated LineVul (99.6%/99.7%) and validation-calibrated ReGVD (98.1%/97.5%) rows immediately visible. The LineVul calibrated row is renamed "calibrated sensitivity" and §5.3 explicitly states that these rows are operating-point sensitivity evidence, not deployment recommendations.
- **A label-specific Fisher exact test table** (Table 9, `tab:rq3-public-tests`) with vulnerable vs. non-vulnerable flip rates, 95% CIs, odds ratios, p-values, and an interpretation column for VulBERTa, LineVul fixed, LineVul calibrated, and validation-calibrated ReGVD. VulBERTa shows vulnerable pairs are more fragile (OR = 1.38, p = 2.1×10⁻⁹).
- **An explicit composition-scope caveat** acknowledging that the composition probe rests on local-family baselines and that public-checkpoint composition runs are out of scope under the current compute budget.
- **A scope statement on LLM-based detectors** in the introduction, explaining why they are out of scope.
- **A fix to the dead-code carrier identifiers**: Listing 1 now uses `rvd_dead_branch` (not `__dead`), and §4.2 confirms with a post-generation scan that no transformation-inserted double-underscore reserved-identifier markers appear in any output file.
- **Median token counts** (per VulBERTa and LineVul tokenizers) in Table 1 instead of median characters.
- **Footnotes/daggers** distinguishing full-test rows from 512-origin subset rows in Table 4.
- **A clean LineVul PR-AUC < 0.5 explanation** in §5.3.
- **A forward reference** from §5.4 (truncation) to §6.5 (logistic regression).
- **A note in Table 9 caption** explaining why majority vote is identical to original-only.
- **A merged Discussion §6.2 ("Implications")** consolidating the previous four short subsections.
- **A note on the GraphCodeBERT checkpoint** as a third-party fine-tune (not author-released).
- **A homogeneity assumption note** in §5.2 for the binomial audit power bound.
- **A consistent EVP abbreviation** for "external-validity probes", reducing the previous repetition.
- **A public GitHub URL** in both Data Availability and Code Availability sections.

These changes are responsive and well-executed. My remaining items are small and would not by themselves block acceptance.

---

## 2. Strengths (unchanged from round 2; recap)

- Practically motivated, well-scoped research question for IST's audience.
- Two exact public checkpoints plus an official public graph implementation, evaluated on the full transformed test set with prediction-file integrity checks.
- High-quality semantic audit (κ = 0.975, conservative exclusion, binomial upper bound).
- Honest handling of LineVul/ReGVD calibration sensitivity, now with the predicted-positive columns that make the degeneracy unmistakable.
- Imbalance-aware reporting with explicit scoping of Big-Vul/DiverseVul as probes.
- Paired statistical analysis (bootstrap CIs, McNemar tests, Fisher exact tests, logistic regression).
- Useful harmful/beneficial flip taxonomy and per-transformation breakdown.
- Diagnostic composition + identifier-renaming ablation with an explicit scope caveat.
- Logistic-regression mechanism analysis with reported odds ratios.
- Reproducibility-oriented public repository.

---

## 3. Remaining Minor Items

### m1. Internal numerical inconsistency for the ReGVD validation-calibrated flip rate.

The flip rate for `ReGVD-official, validation-calibrated` appears three different ways in the manuscript:

- §5.3 prose: "a **0.81%** flip rate" (around line 821 in the source).
- Table 4 (`tab:public-exact-slice`): `Flip = 0.008` (i.e., 0.80%).
- Conclusion (§8): "a **0.75%** flip rate" (around line 1485 in the source).

Please reconcile to a single value (presumably 0.008 / 0.81%) throughout.

### m2. The `sun2026syntax` arXiv identifier is invalid.

In `references.bib`:

```
journal = {arXiv preprint arXiv:2602.00305},
year = {2026},
```

arXiv identifiers use `YYMM.NNNNN` where `MM ∈ 01..12`. `2602` is not a valid arXiv month code. If this is a real preprint, please replace it with the correct ID (e.g., `arXiv:2601.NNNNN` or `arXiv:2602.NNNNN` is impossible — only `2601` through `2612` would be valid for 2026). If the citation is a placeholder or forward-looking entry, please replace it with a verifiable source or remove it; the surrounding claims in §2.4 do not strictly depend on this citation.

### m3. Conclusion still overstates the audit coverage.

"the semantic audit verifies the behavioral preservation of generated variants with strong annotator agreement, zero invalid examples, and conservative exclusions" — the abstract has already been tightened to "validates a randomly sampled subset … 95% upper bound of 0.43% on the invalid rate." Please align the conclusion to the same hedged wording so the two are consistent.

### m4. Persistent DOI for the artifact archive.

A GitHub link is good for code, but IST typically also asks for a versioned, citable artifact deposit with a DOI (Zenodo or Figshare). Adding a one-line deposit (e.g., a Zenodo "Save to GitHub" archive) and citing its DOI in Data Availability would close the last reproducibility gap.

### m5. Open follow-ups from round 2 still worth addressing in the prose.

These were questions for the authors in round 2; quick textual answers would improve the paper without requiring more experiments:

- (Q3) In Table 7, ReGVD-structural-local has the opposite identifier-ablation pattern from the lexical baselines (in-vocab = 0.002 < fresh marker = 0.012). One sentence noting this — likely a consequence of the structural feature set not seeing identifier strings the same way — would head off reader confusion.
- (Q4) §6.5 reports VulBERTa truncation OR = 1.04 (ns) and LineVul OR = 1.33 (***). Please state explicitly that these come from two separate per-detector logistic regressions (or, if a joint model with a detector interaction, please say so and report the interaction term).
- (Q5) How are the 11 "uncertain" audit cases distributed across transformation families? Even a single sentence ("concentrated in T8 normalization on Big-Vul snippets that lack `return` context" or similar) would help readers judge whether any precondition should be tightened.
- (Q6) The Table 10 result that calibrated probability averaging gives VulBERTa F1 = 0.675 — higher than any single-transformation row in Table 8 — would benefit from one sentence distinguishing whether the gain is from score smoothing or from the lower post-hoc threshold (an apples-to-apples comparison at threshold = 0.5 across rows would settle it).

### m6. Wording polish.

- §2.4: "Our novelty is therefore not that transformations can expose brittleness in code models." Consider "Our contribution is therefore not …" — "novelty" used as a noun is unusual.
- §3.3: "the expanded eight-transformation suite with identifier renaming, restricted control-flow rewriting, an additional safe dead-code carrier, and return-expression normalization" — "expanded" implies a prior smaller suite that is no longer mentioned; consider just "the eight-transformation suite."
- §5.3, after Table 4: the sentence "this again indicates that the public LineVul row is dominated by calibration and recall limitations" could be tightened now that the predicted-positive column makes it visually obvious.
- Table 4 caption: the LineVul-calibrated row uses the post-hoc clean-F1-optimal threshold. Calibrating on the test set is normally a methodological red flag; please add one phrase to the caption stating explicitly that this is a sensitivity diagnostic, not a deployable calibration (the prose already says this, but the table should be self-contained for skimmers).
- §6.2: "Tool builders can use transformation-based tests as part of pre-deployment validation" — consider noting that the artifact's `scripts/` directory provides the transformation runner so the implication is actionable.

---

## 4. Detailed Scores (Elsevier IST criteria, 1–5 scale)

| Criterion                          | R1 | R2 | R3 | Justification |
|-----------------------------------|:--:|:--:|:--:|---|
| **Originality / Novelty**          | 2 | 3 | 3 | Honest narrowing to "vulnerability-detection-specific instantiation" of an established robustness paradigm. Still a protocol contribution, not a methodological one — appropriate for IST. |
| **Significance / Relevance to IST**| 4 | 4 | 4 | Robustness of SE security tooling, squarely in IST scope. |
| **Soundness of Methodology**       | 3 | 3.5 | 4 | Fisher exact tests for RQ3, predicted-positive columns, identifier-renaming ablation, logistic-regression mechanism analysis, LLM scope statement, reserved-identifier audit — all in. |
| **Quality of Empirical Evaluation**| 3 | 3.5 | 4 | Now appropriately calibrated: each table self-discloses its operating-point regime. |
| **Reproducibility**                | 4 | 4 | 4 | Public code repository; persistent DOI still pending (minor). |
| **Clarity and Presentation**       | 3 | 3.5 | 4 | Subsection consolidation, table footnotes, predicted-positive columns, listing visual polish. |
| **Related Work Coverage**          | 2 | 4 | 4 | Comprehensive coverage of the adversarial-code-model and metamorphic-testing literature. |

**Overall score: 3.9 / 5 — Accept with Minor Edits.**

---

## 5. Recommendation

**Accept with Minor Edits.** The paper has reached the point where the remaining items are textual polish, one numerical typo (m1), and one bibliography fix (m2). None require additional experiments. I would be happy to see the paper move to production once these are addressed.

**Required for camera-ready:**
1. (m1) Reconcile the ReGVD validation-calibrated flip rate to a single value (Table 4 / §5.3 / Conclusion).
2. (m2) Replace or remove the invalid `sun2026syntax` arXiv identifier.

**Strongly recommended:**
3. (m3) Tighten the Conclusion sentence about the audit to match the abstract's hedged wording.
4. (m4) Add a persistent artifact DOI (Zenodo or similar).
5. (m5) Add brief textual answers to round-2 questions 3–6.

**Nice-to-have:**
6. (m6) Minor wording polish as listed.

---

## 6. One-Line Summary for the Editor

A careful empirical study of vulnerability-detector robustness under semantics-preserving code transformations, with exact public-checkpoint evidence, a high-agreement semantic audit, calibrated mechanism analysis, and appropriately scoped conclusions. The remaining items are minor edits and one bibliography fix.
