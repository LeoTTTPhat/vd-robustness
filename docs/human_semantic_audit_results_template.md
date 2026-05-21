# Human Semantic Audit Results Template

Use this template only after two independent C/C++-familiar human annotators
complete `results/semantic_audit/human_semantic_audit_packet.csv`.

Do not paste this into the manuscript with placeholder values.

## Manuscript Replacement Text

Replace the current AI-assisted screening paragraph in
`paper/main.tex` under `Transformation Validation Results` with:

```tex
The human audit targets 40 changed samples per transformation and dataset; for
the rare control-flow rewrite, all changed samples are included. Two
independent C/C++-familiar annotators reviewed 864 transformed variants using
the protocol in the artifact. The annotators achieved <RAW_AGREEMENT>\% raw
agreement and Cohen's $\kappa=<KAPPA>$ over the four labels
\texttt{preserved}, \texttt{preserved\_with\_precondition}, \texttt{invalid},
and \texttt{uncertain}. After adjudication, <PRESERVED> variants were marked
preserved, <PRECONDITIONED> were marked preserved under explicit transformation
preconditions, <INVALID> were marked invalid, and <UNCERTAIN> were marked
uncertain. Invalid variants were excluded before robustness metrics were
computed; uncertain variants are reported separately and excluded from
semantic-validity claims.
```

## Threats To Validity Replacement Text

Replace the current construct-validity paragraph with:

```tex
The main construct validity threat is that a transformation may not preserve
semantics in all contexts. We mitigate this risk through conservative
transformation rules, syntax checks, deterministic pre-audit, and a
two-annotator human semantic audit. The audit reports raw agreement,
Cohen's $\kappa$, adjudicated labels, invalid variants, uncertain variants,
and exclusion decisions. Remaining uncertain variants are treated as a
semantic-validity limitation rather than as confirmed preserved examples.
```

## Values To Fill

- `<RAW_AGREEMENT>`: percentage agreement before adjudication.
- `<KAPPA>`: Cohen's kappa over the four annotator labels.
- `<PRESERVED>`: adjudicated preserved count.
- `<PRECONDITIONED>`: adjudicated preserved-with-precondition count.
- `<INVALID>`: adjudicated invalid count.
- `<UNCERTAIN>`: adjudicated uncertain count.

## Required Checks Before Use

- `annotator1_label` is filled for all 864 rows.
- `annotator2_label` is filled for all 864 rows.
- `adjudicated_label` is filled for all disagreements and all exclusions.
- Invalid examples are listed in the audit summary.
- Uncertain examples are listed in the audit summary.
- Detector metric tables are recomputed after excluding invalid variants.

