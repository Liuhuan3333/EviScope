# SWR-Bench source and adaptation audit

Status: source-integrity and schema audit complete; candidate external
validation source only. No EviScope sample has been selected, converted,
annotated, or declared gold by this audit.

## Pinned source

The official repository was cloned into the ignored private external-data
area and pinned at commit
`67ae1d4395ac05f800d62b0e13678eadeb9fa5c7` (2026-06-05). The worktree was
clean during this audit.

| Artifact | SHA-256 |
|---|---|
| `data/swr_datasets_d5c5.jsonl` | `7048e7a92ea9f7a1e6812646694a040582448cc1dd9d515264a4b55071aff95d` |
| repository `LICENSE` | `568f99d2d8ac1f8a41402078816325f7a80d38c3e94432975e398584126ae9bf` |

The released repository is MIT-licensed. That fact does not by itself settle
the attribution or redistribution obligations of content originating from the
12 underlying repositories; those obligations must be reviewed before any
public derivative release.

## Read-only dataset audit

- 1,000 unique PR instances: 500 `change_introduced=true` and 500 false.
- 12 Python repositories; no duplicate `instance_id` values.
- 949 listed changes across the 500 positive PRs; label/change-list
  consistency held for all 1,000 records.
- All 1,000 `base_commit` values were valid 40-character SHAs and all PR
  creation timestamps were parseable (2011-04-18 through 2025-04-15).
- No exact repository/PR overlap was found with the four currently frozen
  EviScope Pilot PRs.
- All 949 change-introducing SHAs occurred in `pr_commits` and in the PR
  timeline. Resolution SHAs were outside `pr_commits` and occurred in the
  extended `all_commits` set when present.
- Commit records contain author, committer, and email identity fields. These
  fields are prohibited from EviScope model inputs and derived releases.

Repository counts were: astropy 120, django 11, matplotlib 153, seaborn 9,
flask 7, requests 28, xarray 79, pylint 50, pytest 35, scikit-learn 255,
sphinx 22, and sympy 231.

## Temporal and comment-linkage finding

SWR-Bench's official generation path uses PR title, description, and the
structured diffs in `pr_commits` as the main review input. EviScope-SWR adopts
that narrow field allowlist. It does not expose `changes`, labels, discussion,
timeline, extended commits, or fix information to a model.

Of 949 change records, 939 had a timeline event at the declared
`first_mention_timestamp`. After conservative Markdown/whitespace
normalization, 437 original reviewer comments matched a same-timestamp event
exactly and 322 had a containment match; 190 remained unlinked, and 10 had no
same-timestamp event. Therefore `original_reviewer_comment` must not be
silently treated as a deterministically reconstructed event. A converter must
record linkage status and quarantine unresolved cases before sampling.

The first mention equaled the first review/comment interaction for 240 changes
and followed it for 709. This is expected for later findings in a review but
means that `first_mention_timestamp` is not a universal PR-level snapshot
cutoff. EviScope's safe first adapter therefore uses the official pre-review
generation fields and independently verifies every reconstructed snapshot;
it does not infer visibility from commit author timestamps alone.

## Non-inheritance and analysis boundary

SWR-Bench labels answer a different task from EviScope's atomic-claim evidence
verdicts. Consequently:

- `change_introduced=true` is not an EviScope `SUPPORTED` label;
- a clean PR does not make an arbitrary generated claim `CONTRADICTED`;
- reviewer comments, discussions, and later fixes are provenance/audit data,
  not model-visible evidence;
- SWR-Bench's balanced 500/500 construction cannot estimate natural PR or
  claim prevalence;
- SWR-Bench's prior human verification is valuable source evidence but does
  not replace EviScope's independent A/B annotation and third-human
  adjudication of every disagreement;
- model or LLM-judge outputs cannot become human gold.

Any accepted derivative is reported as `EviScope-SWR`, separately from
`EviScope-Core`. Splits are repository-level, and exact/near-duplicate checks
must run both within SWR and across the Core/SWR layers.

## Current decision and next gate

The source is suitable as an external sampling frame, but it is not yet an
EviScope analysis dataset. Before any model run, the project must freeze a
deterministic conversion/linkage rule, choose a sample without viewing model
outputs, reconstruct and hash review-time snapshots, run leakage and overlap
checks, and then apply the registered EviScope human workflow.

The machine-readable boundary is
`configs/swrbench_adaptation_protocol_v0.1.json`. This audit does not alter the
formal 48-comment Pilot or any frozen annotation artifact.

## Deterministic candidate-adapter result

`scripts/adapt_swrbench_candidates.py` was run over all 1,000 pinned records.
The current derived artifact is the private `adapter-v0.1.2` directory. It
contains 1,000 sanitized candidate-input records, 949 private change-linkage
audit records, and a hash-recorded manifest. It performed no sampling and its
manifest marks model inference, snapshot verification, and gold analysis as
false.

The conservative linker accepted only a unique raw-exact or
whitespace-normalized-exact body at the same timezone-aware instant. It linked
374/949 changes: 104 raw-exact and 270 whitespace-normalized-exact. It
quarantined 575 changes: 494 containment-only, 71 same-time text mismatches,
and 10 without a same-time event. No resolution commit appeared in the
candidate `pr_commits` input.

All structured author, committer, and email fields were removed. A separate
free-text scan found email-like strings in 45 candidate records: 4 occurrences
in PR statements, 30 in commit messages, and 1,416 in diff patches. Diff
occurrences may be executable/test literals, so they were not silently
redacted. This is one reason the candidate corpus remains ineligible for model
inference pending a registered metadata-redaction and code-literal policy.

The manifest SHA-256 is
`45f040424090823f5cc47966b1d6b3b5b644eb64da108ad3a436437f2d79234a`.
Earlier private `adapter-v0.1` and `adapter-v0.1.1` directories are retained as
superseded engineering history and must not be selected or analyzed.

## Review-time and metadata policy result

The frozen candidate policy is
`configs/swrbench_review_time_policy_v0.1.json`. Its cutoff is the earliest
timezone-aware `comment`, `review`, or `review_comment` event. A commit's
committer `date` is treated only as a necessary, not sufficient, condition for
PR visibility. A missing cutoff, any commit after the cutoff, or a
non-contiguous safe prefix quarantines the entire PR.

All 1,831 candidate commits mapped uniquely by SHA to timeline commit events,
and their message, `diff_text`, and structured diff fields matched exactly.
However, 19 PRs had 29 commits after the first-human cutoff. In every affected
PR the first commit was already late, so no non-empty safe prefix existed. The
policy quarantined all 19 rather than deleting individual commits. The
remaining 981 records are only
`timestamp_consistent_requires_repository_verification_not_inference_not_gold`.

The metadata rule removed 23 complete identity trailer lines and replaced 8
other email-like strings in PR statements or commit messages. Independent
verification found zero remaining email-like strings in those metadata fields
and zero diff mismatches. All 1,416 email-like code literals in diff patches
were preserved. The output contains no SWR labels or post-review fields.

The private `review-time-v0.1` manifest SHA-256 is
`4365d0f5e2c39ba989cb5f5021f01167972e2167c057088b1bfbea40c8cf6a1b`.
Its controls keep sampling, model inference, gold analysis, and repository
reconstruction completion false. The next gate is independent verification of
repository commit objects, base/ancestry, and reconstructed diffs; timestamp
consistency alone must not be relabelled as a verified review-time snapshot.
