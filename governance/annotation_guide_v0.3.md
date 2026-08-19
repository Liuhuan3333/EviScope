# EviScope annotation guide v0.3

Status: protocol candidate for the Gate 1 pilot. This version supersedes v0.2
for new work. v0.1/v0.2 artifacts remain protocol history and must not be
silently relabelled.

## 1. Mandatory two-stage workflow

Stage S (screening) decides whether one target review comment is `MATERIAL` or
`NON_MATERIAL` and, only for material comments, freezes atomic claims. Stage V
(verdict) starts only from an adjudicated Stage-S record. Annotators may not
inspect repository evidence, author replies, later commits, or verdicts during
Stage S. Stage-V annotators may not change claim text or source fragments.

## 2. Target eligibility and non-material reasons

PR-author replies are context only. Bot comments are excluded unless the bot is
a registered model condition. Greetings, acknowledgements, process updates,
duplicate pointers, pure preferences, and pure code suggestions without an
explicit prose factual premise are non-material. Questions are material only
when they contain an explicit or necessary factual premise. Registered reasons:

`GREETING_OR_ACKNOWLEDGEMENT`, `PURE_PREFERENCE`, `PURE_CODE_SUGGESTION`,
`PROCESS_UPDATE`, `QUESTION_NO_FACTUAL_PREMISE`, `DUPLICATE_POINTER`,
`CONTEXT_ONLY_PR_AUTHOR`, `OVERSIZED_COMPOSITE`, and `OTHER`.

The oversized threshold remains an embedded executable block longer than 50
lines or body text longer than 2,000 Unicode code points.

## 3. Atomic claims and non-contiguous grounding

An atomic claim is the smallest proposition that can independently receive a
different verdict. Each claim has:

- `normalized_text`: a grammatical, semantics-preserving proposition written
  without consulting evidence;
- one or more ordered, non-overlapping `source_fragments`, each containing an
  exact character span and exact source text.

Multiple fragments are allowed only when syntax shares material words (for
example a subject shared by two predicates). Normalization must not add or
remove hedging, causality, quantifiers, conditions, or certainty. Differences
in normalization are segmentation disagreements and require adjudication.

Stage-S `NON_MATERIAL` records contain zero claims and one registered reason.
Stage-S `MATERIAL` records contain at least one claim and a null reason.

## 4. Evidence boundary and progressive verdict

Only artifacts available at `review_timestamp` are allowed. L0 is the
review-time diff; L1 adds changed-file before/after and enclosing symbols; L2
adds definitions, references, callers/callees, imports, tests, and repository
configuration; L3 adds the PR description, linked issue, repository
documentation, and history available at review time. External web pages and
post-review state are forbidden.

At each level record `SUPPORTED`, `CONTRADICTED`, or `INSUFFICIENT`. Continue
only after `INSUFFICIENT`, and stop after the first decisive verdict. If L3 is
insufficient, the final verdict is `INSUFFICIENT` and minimum level is null.
Every decisive judgment cites raw, hashed artifact IDs.

## 5. Independence, leakage, and dependence

A and B work independently in both stages. Stage-S A/B exports are frozen
before adjudication; the adjudicated Stage-S file is then frozen before Stage V.
The adjudicator is a third person and LLM majority vote is forbidden. At least
one human annotator must read the target language. Repository, PR, thread, and
actor identifiers remain available for clustered analysis. At least 20% of
verdict records receive reverse verification from the complete evidence package.

Generated summaries, evaluator prose, gold labels, author acceptance, and
post-review fixes must never enter model evidence packages. `normalized_text`
is the model claim input but is not evidence.

## 6. Disagreement codes

`SEGMENTATION_BOUNDARY`, `NORMALIZATION`, `MATERIALITY`, `VERDICT`,
`MINIMUM_LEVEL`, `EVIDENCE_SCOPE`, `REVIEW_TIME_LEAKAGE`, and `OTHER`.

## 7. Revision log

| Version | Date | Change | Reason | Affects prior labels? |
|---|---|---|---|---|
| v0.1 | 2026-08-14 | Initial protocol | Gate 0 | no |
| v0.2 | 2026-08-16 | Role, suggestion, duplicate, long-comment and dependence rules | Real-PR screening | no formal labels |
| v0.3 | 2026-08-17 | Separate screening/verdict stages; allow exact non-contiguous fragments plus normalized claims | Guided calibration exposed zero-claim and shared-subject defects | no formal labels; synthetic fixtures only |
