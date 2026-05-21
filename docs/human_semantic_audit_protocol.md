# Human Semantic Audit Protocol

## Goal

Assess whether transformed vulnerability-detection benchmark variants preserve
the source-level behavior and vulnerability label of the original function.

## Audit Unit

Each audit unit is one transformed function variant paired with its original
function. The auditor sees:

- dataset,
- source identifier,
- transformation name,
- original function,
- transformed function,
- transformation validation note,
- target label.

## Sampling Plan

Use 30--50 changed variants per transformation per dataset when enough changed
variants exist. For rare transformations, audit all changed variants. The
current expanded sample uses 40 variants per dataset/transformation and all
available control-flow rewrites.

## Annotators

Use two independent human annotators with C/C++ familiarity. Annotators must
work independently before adjudication.

Recommended minimum qualifications:

- at least one year of C/C++ programming experience, or
- prior vulnerability-detection/data-labeling experience, or
- graduate-level software engineering/security coursework.

## Decisions

Annotators assign one of four labels:

- `preserved`: the transformation is semantics-preserving for the visible
  function snippet.
- `preserved_with_precondition`: preservation depends on the stated
  transformation precondition, e.g., local identifier scope or unreachable
  branch guard.
- `invalid`: the transformation likely changes behavior, vulnerability status,
  compilation, or external binding.
- `uncertain`: the snippet lacks enough context to decide.

## Invalid-Variant Examples

Mark `invalid` when any of the following occur:

- Identifier renaming changes an externally visible symbol, macro name, struct
  field, function call target, or string-reflected name.
- Dead code introduces declarations that shadow existing variables in a way
  that can change compilation.
- Control-flow rewriting changes branch side effects, short-circuit behavior,
  fall-through behavior, or return order.
- Normalization changes operator precedence, macro expansion behavior, volatile
  access behavior, or undefined-behavior exposure.
- Comment insertion breaks preprocessor directives or macro continuations.

## Disagreement and Adjudication

After independent annotation:

1. Compute raw agreement and Cohen's kappa over the four labels.
2. Resolve disagreements by joint discussion.
3. Record both original labels, adjudicated label, and adjudication note.
4. Exclude `invalid` variants from detector-result tables.
5. Report `uncertain` variants separately in threats to validity.

## Reporting Requirements

The paper should report:

- number of audited variants by dataset and transformation,
- raw agreement,
- Cohen's kappa,
- number and percentage of `invalid` and `uncertain` variants,
- examples of invalid and uncertain cases,
- whether invalid variants were excluded before computing robustness metrics.

## Current Status

The existing file `results/semantic_audit/expanded_semantic_audit.csv` is a
completed deterministic pre-audit over transformed variants. It is useful for
screening, but it is not a substitute for the two-annotator human audit above.
