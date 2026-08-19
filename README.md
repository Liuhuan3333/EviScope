# EviScope FSE 2027 experiment scaffold

This directory is the executable research artifact for the EviScope project. It
is intentionally separate from `../EviReview`: the older repository remains a
historical prototype and its six hand-written tasks are not evidence for this
study.

## Gate 0 scope

Gate 0 freezes the task vocabulary and makes resource assumptions auditable.
It does **not** claim that annotators, compute, model access, or budget have been
confirmed. The current machine-readable status is in
`governance/gate0_status.json`.

## Quick start

The validation path uses only Python's standard library and requires Python
3.10 or newer (the source uses PEP 604 union type syntax). Bash is needed only
for the optional server-collection wrapper; all validation entry points are
Python and run on Linux and macOS.

```bash
python3 scripts/validate.py --all
python3 -m unittest discover -s tests -v
```

On the laboratory server, collect a non-secret environment inventory:

```bash
bash scripts/collect_server_env.sh server_environment.json
python3 scripts/validate.py server_environment.json
```

The collector records hardware and tool versions. It never prints environment
variable values, API keys, SSH configuration, usernames, hostnames, network
addresses, or process command lines. Inspect the result before sharing it.

Before reconstruction, verify that the exact review-time commits are already
available in a local clone (this command never fetches or mutates the clone):

```bash
python3 scripts/snapshot_preflight.py /path/to/clone BASE_SHA HEAD_SHA
```

Passing this preflight is necessary but not sufficient for Gate 0: run it on a
real public PR and audit timestamps and license before marking the criterion
confirmed.

For inline-review data, build separate L0 packages from each comment's
`original_commit_id`; never substitute the PR's final head for an earlier
review state:

```bash
python3 scripts/build_review_snapshots.py \
  --repository /path/to/clone \
  --comments /path/to/inline_comments.json \
  --final-base BASE_SHA \
  --output /private/path/review-snapshots
```

The builder computes a merge base for every distinct review head, disables
external diff and text-conversion drivers, hashes each binary L0 diff, and
refuses missing, empty, or pre-existing outputs.

From a frozen L0 snapshot, reconstruct review-time L1 evidence (changed-file
before/after and enclosing symbols) without checking out HEAD or using later
GitHub state:

```bash
python3 scripts/build_l1_evidence.py \
  --repository /path/to/clone \
  --snapshot-dir /private/path/review-snapshots/REVIEW_HEAD \
  --comments /path/to/inline_comments.json \
  --comment-id COMMENT_ID \
  --output /private/path/l1-evidence/COMMENT_ID
```

L1 packages are not gold. They refuse overwrite, hash every artifact, and
only read merge-base and review-head Git objects named in the L0 metadata.

## Resource confirmation

1. Create `data/private/` and copy `governance/resources.example.json` to
   `data/private/resources.json`. This directory is ignored; do not put names
   or private IDs in `governance/`.
2. Replace `unconfirmed` only after the responsible person explicitly agrees.
3. Record compute partitions, quotas, permitted model endpoints, and budget
   ceilings without storing credentials.
4. Run the validator and update `governance/gate0_status.json` from evidence;
   do not mark the gate passed merely because the schema validates.

## Pilot workflow

1. Read `governance/annotation_guide_v0.3.md`. Versions v0.1 and v0.2 are
   protocol history; all new pilot work must identify guide v0.3.
2. Run blinded Stage S first using
   `schemas/materiality_screening.schema.json`. Stage-S annotators see only the
   comment text and must not see repository context, author replies, verdicts,
   or model predictions.
3. Freeze independent A/B exports before third-person adjudication. Stage V may
   start only from a hashed, adjudicated `MATERIAL` screening record and must
   not change its claim IDs, normalized text, or source fragments.
4. Use `schemas/annotation_v0.3.schema.json` for Stage V and preserve the
   progressive L0-L3 stopping rule. Decisive judgments must cite raw hashed
   artifacts available at review time.
5. Validate manifests before annotation. `--all` checks Stage-S fragment
   spans, Stage-S hashes and frozen claim IDs, annotation evidence levels, and
   Pilot references against tracked synthetic fixtures.
6. Keep annotator A and B outputs separate until both are frozen. Preserve raw
   invalid model outputs and never treat model smoke as annotation or gold.

The offline Stage-S CLI is `scripts/annotate_stage_s.py`. It accepts only a
blinded packet containing `sample_id` and `comment_text`, supports resumable
checkpoints, computes Unicode fragment offsets from unique verbatim text, and
produces a hash-recorded, non-overwritable export. See
`governance/stage_s_annotator_operations_v0.1.md`. Do not use the formal
48-comment packet until Gate authorization.

## SWR-Bench external candidate audit

SWR-Bench is an external sampling frame, not EviScope gold and not part of the
formal 48-comment Pilot. The deterministic adapter verifies the pinned source
hash, strips structured identity fields, copies only the registered candidate
field allowlist, audits reviewer-comment linkage without emitting raw comment
text, and refuses to overwrite an existing output directory:

```bash
python3 scripts/adapt_swrbench_candidates.py \
  --dataset data/private/external/swrbench/source/data/swr_datasets_d5c5.jsonl \
  --protocol configs/swrbench_adaptation_protocol_v0.1.json \
  --output data/private/external/swrbench/adapter-v0.1.2
```

The resulting candidate inputs remain explicitly ineligible for sampling,
model inference, and gold analysis until a separate review-time snapshot rule
is frozen and verified. See `governance/swrbench_adaptation_audit_2026-08-18.md`.

The registered temporal and metadata policy is
`configs/swrbench_review_time_policy_v0.1.json`. Apply it only to the pinned
source and adapter manifest:

```bash
python3 scripts/prepare_swrbench_review_time_candidates.py \
  --dataset data/private/external/swrbench/source/data/swr_datasets_d5c5.jsonl \
  --adaptation-protocol configs/swrbench_adaptation_protocol_v0.1.json \
  --adapter-manifest data/private/external/swrbench/adapter-v0.1.2/manifest.json \
  --policy configs/swrbench_review_time_policy_v0.1.json \
  --output data/private/external/swrbench/review-time-v0.1
```

Passing this timestamp audit is necessary but not sufficient. The output stays
inference-ineligible until repository commit objects, base/ancestry, and an
independently reconstructed diff have also been verified.

## Layout

```text
configs/                 frozen experiment and model configuration
schemas/                 JSON Schema contracts
governance/              Gate status, resource template, annotation guide
data/manifests/           reconstruction/pilot manifests (no cloned corpora)
scripts/                  environment collection, snapshots, L1 evidence, validation
src/                      dependency-free validators and evidence builders
tests/                    validator and reconstruction regression tests
```

No API key belongs in this tree. Use the server's secret manager or environment
injection and record only the environment-variable **name** in model config.
