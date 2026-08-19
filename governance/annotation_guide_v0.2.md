# EviScope annotation guide v0.2

Status: pilot protocol candidate. This version supersedes v0.1 for all new
pilot annotations. No formal annotation produced under v0.1 may be silently
relabelled; any migration must be logged and repeated independently.

## 1. Target comment eligibility

The target unit is a review comment written by a human reviewer or produced by
a registered review model. Determine eligibility before claim segmentation.

- A pull-request author's replies are `CONTEXT_ONLY_PR_AUTHOR`. Preserve them
  as thread context, but do not treat them as target review comments.
- A review summary that only points to inline comments is a
  `DUPLICATE_POINTER`; it must not create duplicate claims.
- Greetings, acknowledgements, approval-only text, process updates and pure
  preferences are `NON_MATERIAL`.
- A pure code suggestion with no explicit truth-evaluable premise is
  `PURE_CODE_SUGGESTION` and is non-material. If accompanying prose states a
  behavioral, correctness, compatibility or test claim, segment only that
  factual proposition; do not turn the recommendation itself into a claim.
- A question is material only when it contains an explicit or necessary
  factual premise. Segment the premise, not the request for an answer.
- Bot comments are excluded unless the bot is a registered model condition.

Record a stable anonymized actor ID, actor role, comment kind, reply ID and
thread-root ID in the private screening table. Never publish account names.

## 2. Atomic claim segmentation

An atomic claim is the smallest material proposition in a target comment that
can independently be supported, contradicted, or left unresolved. Split claims
joined by causal or conjunctive language when either part could receive a
different verdict. Preserve exact character offsets into the original comment.

Hedges such as "might" affect the proposition's strength but do not by
themselves make it non-material. Do not strengthen a tentative claim during
normalization.

Example: “This can return null, so the caller will crash” normally contains two
claims: the return-value claim and the downstream-effect claim.

Use one of these reason codes when no target claim is produced:

- `GREETING_OR_ACKNOWLEDGEMENT`
- `PURE_PREFERENCE`
- `PURE_CODE_SUGGESTION`
- `PROCESS_UPDATE`
- `QUESTION_NO_FACTUAL_PREMISE`
- `DUPLICATE_POINTER`
- `CONTEXT_ONLY_PR_AUTHOR`
- `OVERSIZED_COMPOSITE`
- `OTHER`

## 3. Oversized composite comments

For the Gate 1 pilot, a comment is `OVERSIZED_COMPOSITE` when it contains an
embedded executable block longer than 50 lines or more than 2,000 Unicode code
points of body text. Retain it in the attrition log but exclude it from the
ordinary calibration sample. Do not cherry-pick a convenient subset of its
claims. A later study may define a separate long-comment stratum before viewing
test outcomes.

## 4. Evidence boundary

Only artifacts available at the target comment's recorded `review_timestamp`
may be used.

- L0: review-time patch/diff only.
- L1: L0 plus changed-file before/after and enclosing function/class.
- L2: L1 plus definitions, references, callers/callees, imports, tests and
  repository configuration.
- L3: L2 plus PR description, linked issue, repository documentation and
  history available at review time.

External web pages and post-review commits are forbidden. A later fix, reply,
developer acceptance or review approval may be recorded as metadata but cannot
establish the gold verdict. Earlier discussion may guide retrieval, but another
person's assertion is not decisive evidence without a traceable repository
artifact.

## 5. Progressive decision procedure

For each material claim, examine K0, K1, K2 and K3 in order. At each level
record:

1. `SUPPORTED` if the package contains decisive support;
2. `CONTRADICTED` if it contains decisive conflicting evidence;
3. `INSUFFICIENT` if neither conclusion is warranted.

Continue upward only after `INSUFFICIENT`. `minimum_evidence_level` is the first
level with a supported or contradicted verdict. It is `null` when K3 remains
insufficient. Cite exact artifact IDs and locations; explanations written by a
dataset curator are not evidence.

## 6. Thread and sampling dependence

Store repository, PR, thread root and anonymized actor identifiers. Replies in
the same thread are correlated observations and must not be counted as
independent evidence of prevalence or effectiveness. Pilot selection should
cap domination by one PR, one thread or one reviewer. Formal uncertainty must
be clustered at least by repository/PR as specified in the analysis plan.

## 7. Confidence

- high: direct executable, syntactic, or explicit documentary evidence;
- medium: strong repository-local inference with no material alternative;
- low: plausible but disputable interpretation.

Low confidence does not change the verdict. It flags adjudication priority.

## 8. Independent workflow

Annotators A and B work independently and cannot view each other's records.
After both exports are frozen, compute agreement for segmentation/materiality,
three-state verdict and beyond-diff (`L*>L0`). The adjudicator receives both
records and raw artifacts, records a reasoned decision, and never resolves a
disagreement by LLM majority vote. At least one annotator must be able to read
the target language.

At least 20% of pilot records receive reverse verification from the complete
evidence package to detect anchoring caused by progressive disclosure.

## 9. Leakage checks

Reject a record if artifact packages contain evaluator prose, gold labels,
post-review state, or a generated summary that reveals the intended answer.
Artifact text must be raw and traceable by hash to its origin.

## 10. Required disagreement codes

- `SEGMENTATION_BOUNDARY`
- `MATERIALITY`
- `VERDICT`
- `MINIMUM_LEVEL`
- `EVIDENCE_SCOPE`
- `REVIEW_TIME_LEAKAGE`
- `OTHER`

## 11. Pilot revision log

| Version | Date | Change | Reason | Affects prior labels? |
|---|---|---|---|---|
| v0.1 | 2026-08-14 | Initial protocol | Gate 0 | no |
| v0.2 | 2026-08-16 | Added target-role, pure-suggestion, duplicate-pointer, oversized-comment and thread-dependence rules | Real-PR smoke screening exposed ambiguous inclusion decisions | no formal labels exist; synthetic fixture updated |
