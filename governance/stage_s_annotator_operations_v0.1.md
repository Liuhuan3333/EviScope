# Stage-S annotator operations v0.1

Status: tooling instructions for guide v0.3. Formal Pilot Stage S on the
hashed 48-pack is authorized by
`governance/stage_s_pilot_authorization_2026-08-19.md` under the SANER Agentic
venue lock. Calibration remains training-only and is not gold.

## Before annotation

1. Read `governance/annotation_guide_v0.3.md` completely.
2. Confirm that A and B have different private IDs and different output
   directories. Do not put names in either directory.
3. Confirm the input SHA-256 out of band. A and B must receive byte-identical
   copies of the same `stage_s_inputs.json`.
4. Do not open `private_sample_map.json`, repository data, diffs, author
   replies, model smoke outputs, or the other annotator's directory.

The CLI rejects input samples containing fields other than `sample_id` and
`comment_text`. It does not load the private sample map.

## Synthetic practice

Use a disposable directory, not a formal annotation directory:

```bash
python3 scripts/annotate_stage_s.py \
  --inputs tests/fixtures/stage_s_inputs.synthetic.json \
  --output-dir /tmp/eviscope-stage-s-synthetic-a \
  --annotator-private-id synthetic-a-not-a-person \
  --round independent_a
```

This fixture is fabricated and must never enter analysis.

## Maven non-Pilot calibration

This calibration is training, not formal Pilot annotation and not gold. The
coordinator gives A and B only this file:

`data/private/calibration/stage-s-maven-11639-v0.1/stage_s_inputs.json`

Do not give annotators `private_sample_map.json`, raw PR files, existing
calibration answers, or each other's output. Use these separate sessions:

```bash
python3 scripts/annotate_stage_s.py \
  --inputs data/private/calibration/stage-s-maven-11639-v0.1/stage_s_inputs.json \
  --output-dir data/private/annotations/stage-s-calibration/annotator_A01 \
  --annotator-private-id annotator_A01 \
  --round independent_a

python3 scripts/annotate_stage_s.py \
  --inputs data/private/calibration/stage-s-maven-11639-v0.1/stage_s_inputs.json \
  --output-dir data/private/annotations/stage-s-calibration/annotator_B01 \
  --annotator-private-id annotator_B01 \
  --round independent_b
```

A and B must freeze their exports before the coordinator compares them.
Agreement items pass through unchanged. Every disagreement is placed in a
disagreement-only packet for `adjudicator_C01`; A and B must not revise labels
through post-hoc discussion instead of third-person adjudication. The
adjudicator need not inspect agreement items and must not see model outputs.
Calibration records must not be copied into the formal Pilot dataset.

## Formal Pilot Stage S (authorized)

Working pack:

`data/private/annotations/stage-s-pilot-v0.1/`

Blinded input SHA-256 must be:

`657d6525769fb855d8e33a2f4139a044877b61cbc2aedb387db4e8e75b7e5a09`

```bash
python3 scripts/annotate_stage_s.py \
  --inputs data/private/annotations/stage-s-pilot-v0.1/blinded/stage_s_inputs.json \
  --output-dir data/private/annotations/stage-s-pilot-v0.1/annotator_A01 \
  --annotator-private-id annotator_A01 \
  --round independent_a

python3 scripts/annotate_stage_s.py \
  --inputs data/private/annotations/stage-s-pilot-v0.1/blinded/stage_s_inputs.json \
  --output-dir data/private/annotations/stage-s-pilot-v0.1/annotator_B01 \
  --annotator-private-id annotator_B01 \
  --round independent_b
```

See `data/private/annotations/stage-s-pilot-v0.1/START_HERE.md` for the
annotator-facing start pack. C prepares by reading the guide now and waits
until both independent exports are frozen.

## Independent A/B run mechanics

Never exchange checkpoints or frozen exports before both exports are frozen.

For each comment:

- choose `MATERIAL` or `NON_MATERIAL`;
- choose non-material reasons only from the displayed registered list;
- for a material claim, write a semantics-preserving normalized proposition;
- paste each source fragment verbatim and finish it with a line containing
  only `<<<END>>>`;
- if a quotation occurs zero or multiple times, the CLI rejects it instead of
  guessing offsets or editing the text.

Entering `Q` saves the checkpoint and exits. Re-run the same command to resume.
Before export, a record can be replaced with `--redo SAMPLE_ID`.

## Freeze and handoff

When every sample is complete, answer `y` to freeze or run:

```bash
python3 scripts/annotate_stage_s.py \
  --inputs data/private/annotations/stage-s-pilot-v0.1/blinded/stage_s_inputs.json \
  --output-dir data/private/annotations/stage-s-pilot-v0.1/annotator_A01 \
  --annotator-private-id annotator_A01 \
  --round independent_a \
  --export-only
```

The CLI validates every record, writes `frozen_export/records/*.json`, records
their SHA-256 values in `frozen_export/manifest.json`, and then marks the
checkpoint frozen. Frozen exports are not gold and cannot be overwritten.

Report only the input hash, export manifest hash, record count, and completion
status to the coordinator. Do not send labels to the other annotator. A third
person may begin adjudication only after both independent exports are frozen,
and receives only the resulting disagreement items.
