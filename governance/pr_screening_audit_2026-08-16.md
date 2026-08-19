# Gate 0 PR screening audit — 2026-08-16

Status: preliminary corpus-screening evidence, not gold annotation and not a
model evaluation result.

## Inputs and integrity

| PR | Role-screening records | Reviewer records | PR-author context | License | L0 diff SHA-256 |
|---|---:|---:|---:|---|---|
| `pytest-dev/pytest#14781` | 4 inline comments | not frozen in this audit | not frozen in this audit | MIT | `8d5dc6a94a733ccf96c2720b0d3cd731c0fcfd0585c484e492e1b776f333460f` |
| `scikit-learn/scikit-learn#34412` | 32 | 23 | 9 | BSD-3-Clause | `8fe76f35118a461b4c4b511f6d121cdacab6fb15b0a3a9212b4214a27f3e4695` |
| `spring-projects/spring-framework#36899` | 16 | 14 | 2 | Apache-2.0 | `8059b8dc497bd0e30298d1c272ca19eee63ffd22cc6bf605608bf9d346791c84` |

The combined anonymized screening input for the latter two PRs contained 48
records and had SHA-256
`2ad99f810e449175274a3582ca3fa77b46d5fe5fa4d5779630d8052207c6f84f`.
The raw GitHub payloads remain private working data; public artifacts must not
expose account names.

## Preliminary attrition

| PR | Eligible material | Question with factual premise | Oversized composite | Duplicate pointer | Non-material | PR-author context |
|---|---:|---:|---:|---:|---:|---:|
| `scikit-learn#34412` | 11 | 2 | 1 | 2 | 7 | 9 |
| `spring-framework#36899` | 2 | 0 | 0 | 2 | 10 | 2 |

These counts were produced by one researcher's protocol screening. They do not
replace independent A/B segmentation or adjudication and must not be reported
as prevalence estimates.

## Selection decision

- `pytest#14781`: snapshot and pipeline smoke only; exclude from formal results.
- `scikit-learn#34412`: retain as a primary Gate 1 pilot candidate. It contains
  claims about array namespaces/devices, memory order, call relationships,
  numerical stability, tests and empirical behavior, so multiple evidence
  levels may be exercised.
- `spring-framework#36899`: exclude from the primary pilot; retain as a
  low-density screening control. Most reviewer records are pure or repeated
  mechanical suggestions, and all reviewer records come from one actor.

## Bias controls adopted

1. PR-author replies are context only.
2. Pure code suggestions without explicit factual premises are non-material.
3. Pointer-only review summaries do not duplicate inline claims.
4. Oversized composite comments are logged but excluded from the ordinary
   pilot stratum under the predeclared v0.2 threshold.
5. Repository, PR, thread and actor clustering must be preserved.

## Connector triage extension

The following candidates were inspected through their public GitHub pull
request metadata, inline review threads and submitted reviews. They have not
yet been reconstructed or frozen locally, so the counts below are discovery
metadata rather than corpus facts.

| Candidate | Inline threads | Human reviewer actors | Preliminary decision | Rationale |
|---|---:|---:|---|---|
| `pytest-dev/pytest#14523` | 17 | 2 | retain | Contains factual claims about stable APIs, iterator/iterable behavior, truncation, formatting cost and existing tests; moderate size. |
| `spring-projects/spring-framework#36641` | 3 | 1 | retain provisionally | Java coverage with claims about URI encoding, user-info removal, allocation and log-injection behavior; reviewer diversity is weak. |
| `django/django#20583` | 19 | 4 | retain as reserve/fourth repository | Rich claims about database queries, multi-instance counters, probabilistic culling, configuration and tests; larger annotation burden. |
| `pydantic/pydantic#12907` | 3 | 1 | exclude | Mostly narrow test/documentation edits and one reviewer; insufficient claim diversity. |
| `pydantic/pydantic#12908` | 0 | 0 | exclude | No inline review claims. |
| `pydantic/pydantic#12825` | 5 | 2 | exclude from current scope | Substantive review, but the central implementation is Rust and the frozen pilot scope is Python/Java. |
| `pandas-dev/pandas#66338` | 6 | 1 human | exclude | Five bot comments, repeated placeholder findings and only one substantive human claim. |
| `FasterXML/jackson-databind#5950` | 0 | 0 | exclude | No review claims. |
| `FasterXML/jackson-databind#5888` | 0 | 0 | exclude | No review claims. |

The provisional four-repository set is therefore `scikit-learn#34412`,
`pytest#14523`, `spring-framework#36641`, and `django#20583`. This set is not
frozen: each new candidate must first pass the same review-time snapshot,
license, actor-role and attrition checks already applied to the initial smoke
data. If the Java candidate yields too few eligible claims after reconstruction,
the pilot must be narrowed explicitly to Python rather than silently replacing
it after observing verdict labels.

## `pytest#14523` temporal reconstruction audit

The candidate has 26 inline comments over five distinct
`original_commit_id` values. Seven force-pushed/rebased historical Git objects
were initially unreachable from the final PR ref but were recovered directly
by immutable SHA. Each review head was diffed against its merge base with the
final base ancestry, rather than substituting the final PR head.

- final base: `d02c36266339ec7fab376db2e77d4e55ea165384`
- final head: `8fe130eeb4e0fb995a6fbb42a14baff0df5e4026`
- snapshot count: 5
- comment count: 26
- raw inline-comment SHA-256:
  `0d4cb8640cefd374f94f71dad857f25e2db27c374a7dbe70a7ac18aae757c7b1`
- snapshot-manifest SHA-256:
  `be7b7c45af094e65cb4f57d9784e7ee184f7bb3f9c080b73d71a72e4a15a7806`
- L0 hash verification: 5/5 valid
- file-path anchoring: 26/26
- exact GitHub hunk anchoring: 13/26
- body-exact anchoring after excluding the `@@` range header: 11/26
- changed-line ordered anchoring: 2/26
- unanchored comments: 0/26

The two ordered-line cases remain eligible for materiality screening but must
retain their weaker anchor class. This audit establishes temporal and textual
traceability only; it does not establish claim validity or a gold verdict.

## Remaining decision

Reconstruct and hash the two remaining new candidates, then run role/materiality
screening without viewing any evidence-level verdicts. Gate 1 annotation cannot
begin until the resource criteria in `gate0_status.json` are confirmed.
