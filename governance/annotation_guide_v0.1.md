# EviScope annotation guide v0.1

Status: pilot protocol; revisions are permitted only before the Gate 1 protocol
freeze and must be logged.

## 1. Unit of annotation

An atomic claim is the smallest material proposition in a review comment that
can independently be supported, contradicted, or left unresolved. Split claims
joined by causal or conjunctive language when either part could receive a
different verdict. Preserve exact character offsets into the original comment.

Do not force greetings, hedges, questions without an implied factual premise,
or pure style preferences into factual labels. Mark them `non_material` and
record a reason.

Example: “This can return null, so the caller will crash” normally contains two
claims: the return-value claim and the downstream-effect claim.

## 2. Evidence boundary

Only artifacts available at the recorded `review_timestamp` may be used.

- L0: patch/diff only.
- L1: L0 plus changed-file before/after and enclosing function/class.
- L2: L1 plus definitions, references, callers/callees, imports, tests and
  repository configuration.
- L3: L2 plus PR description, linked issue, repository documentation and
  history available at review time.

External web pages and post-review commits are forbidden in v0.1. A later fix,
reply, or developer acceptance can be recorded as metadata but cannot establish
the gold verdict by itself.

## 3. Progressive decision procedure

For each material claim, examine K0, K1, K2 and K3 in order. At each level record:

1. `SUPPORTED` if the package contains decisive support;
2. `CONTRADICTED` if it contains decisive conflicting evidence;
3. `INSUFFICIENT` if neither conclusion is warranted.

Continue upward only after `INSUFFICIENT`. `minimum_evidence_level` is the first
level with a supported or contradicted verdict. It is `null` when K3 remains
insufficient. Cite exact artifact IDs and locations; explanations written by a
dataset curator are not evidence.

## 4. Confidence

- high: direct executable, syntactic, or explicit documentary evidence;
- medium: strong repository-local inference with no material alternative;
- low: plausible but disputable interpretation.

Low confidence does not change the verdict. It flags adjudication priority.

## 5. Independent workflow

Annotators A and B work independently and cannot view each other's records.
After both exports are frozen, compute agreement for three-state verdict and
beyond-diff (`L*>L0`). The adjudicator receives both records and raw artifacts,
records a reasoned decision, and never resolves disagreement by LLM majority
vote. At least one annotator must be able to read the target language.

At least 20% of pilot records receive reverse verification from the complete
evidence package to detect anchoring caused by progressive disclosure.

## 6. Leakage checks

Reject a record if artifact packages contain evaluator prose, gold labels,
post-review state, or a generated summary that reveals the intended answer.
Artifact text must be raw and traceable by hash to its origin.

## 7. Required disagreement codes

- `SEGMENTATION_BOUNDARY`
- `MATERIALITY`
- `VERDICT`
- `MINIMUM_LEVEL`
- `EVIDENCE_SCOPE`
- `REVIEW_TIME_LEAKAGE`
- `OTHER`

## 8. Pilot revision log

| Version | Date | Change | Reason | Affects prior labels? |
|---|---|---|---|---|
| v0.1 | 2026-08-14 | Initial protocol | Gate 0 | no |

