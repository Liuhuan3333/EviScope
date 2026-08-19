# Stage-V annotator operations v0.1

Status: tooling instructions for guide v0.3. Stage V starts only from
**adjudicated, MATERIAL** Stage-S records with frozen claim IDs and text.
Calibration packets are training-only and are not gold.

## Prerequisites

1. Read `governance/annotation_guide_v0.3.md` completely.
2. Confirm Stage-S A/B exports are frozen and disagreements are adjudicated.
3. Coordinator prepares a Stage-V packet with:
   - `blinded/stage_v_inputs.json` (claims + progressive evidence text)
   - `blinded/dataset_manifest.json` (artifact catalog for validation)
4. Annotators receive only the blinded packet. Do not open `private_sample_map.json`,
   raw PR trees, model smoke outputs, or the other annotator's directory.

## Synthetic CLI practice

```bash
python3 scripts/annotate_stage_v.py \
  --inputs tests/fixtures/stage_v_inputs.synthetic.json \
  --output-dir /tmp/eviscope-stage-v-synthetic-a \
  --annotator-private-id synthetic-v-not-a-person \
  --round independent_a
```

This fixture is fabricated and must never enter analysis.

## Maven calibration (training only)

Coordinator packet:

`data/private/annotations/stage-v-calibration-v0.1/blinded/stage_v_inputs.json`

Verify hashes from `prepare_receipt.json` before annotation.

```bash
python3 scripts/annotate_stage_v.py \
  --inputs data/private/annotations/stage-v-calibration-v0.1/blinded/stage_v_inputs.json \
  --output-dir data/private/annotations/stage-v-calibration-v0.1/annotator_A01 \
  --annotator-private-id annotator_A01 \
  --round independent_a
```

Repeat for B with a separate output directory and `--round independent_b`.

## Progressive verdict rules

1. Claims, `normalized_text`, and `source_fragments` are read-only.
2. Start at L0. Continue to L1/L2/L3 only while the current level is
   `INSUFFICIENT` and the next level exists in the packet.
3. Stop after the first `SUPPORTED` or `CONTRADICTED` judgment.
4. Decisive judgments must cite `artifact_id` values exactly as shown in the
   evidence headers for the current level.
5. Enter `q` at a sample prompt to checkpoint and resume later with the same command.

## Export protocol

1. Complete every sample in the packet.
2. Freeze with `--export-only` or confirm at the final prompt.
3. Report **input hash + dataset manifest hash + export manifest hash + record count**
   to the coordinator.
4. Do not exchange verdict labels before both A/B exports are frozen.

## Coordinator: prepare a packet

After Stage-S adjudication:

```bash
python3 scripts/prepare_stage_v_packet.py \
  --adjudicated-records-dir PATH/TO/adjudicator/frozen_export/records \
  --comment-texts PATH/TO/stage_s_inputs.json \
  --sample-map PATH/TO/private_sample_map.json \
  --pr-candidates-root data/private/pr-candidates \
  --output-dir data/private/annotations/stage-v-pilot-v0.1 \
  --selection-id eviscope-stage-v-pilot-v0.1 \
  --status pre_gate_candidate_not_gold
```

Use `--sample-id` to include specific samples while pilot attrition is still open.

## Forbidden

- Changing claim text or fragment spans during Stage V
- Citing artifact IDs from a future evidence level
- Using post-review GitHub pages or model outputs as evidence
- Copying calibration verdicts into the formal pilot
- Asking an agent to fill formal A/B/C labels
