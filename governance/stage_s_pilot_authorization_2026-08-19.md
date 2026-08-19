# Formal Stage-S authorization — Pilot 48-pack

Status: **authorized to start**  
Authorized at: 2026-08-19  
Authority: project lead under `governance/venue_lock_saner_agentic_2026-08-19.md`  
Guide: `governance/annotation_guide_v0.3.md`

## Staffing confirmation

Project lead confirmed that annotator B and adjudicator C are available in the next few days and may begin now. Private role IDs remain:

- Annotator A: `annotator_A01`
- Annotator B: `annotator_B01`
- Adjudicator C: `adjudicator_C01`

Do not write personal names into this tree.

## Authorized packet

| Field | Value |
|---|---|
| Selection | `eviscope-stage-s-pilot-candidate-v0.1` |
| Canonical path | `data/private/pilot/stage-s-pilot-candidate-v0.1/stage_s_inputs.json` |
| Working blinded copy | `data/private/annotations/stage-s-pilot-v0.1/blinded/stage_s_inputs.json` |
| SHA-256 | `657d6525769fb855d8e33a2f4139a044877b61cbc2aedb387db4e8e75b7e5a09` |
| Samples | 48 |
| Status | still `pre_gate_candidate_not_gold` until adjudicated; this authorization starts labeling, it does not create gold |

`private_sample_map.json` must not be given to A, B, or C.

## Start order

1. **Now:** A and B begin independent Stage S. Zero label discussion until both exports are frozen.
2. **After both freezes:** coordinator builds disagreement-only packet.
3. **Then:** C adjudicates disagreements only.
4. **Never:** open model-smoke outputs, private map, diffs, or each other's directories during Stage S.

## Output directories

```text
data/private/annotations/stage-s-pilot-v0.1/annotator_A01/
data/private/annotations/stage-s-pilot-v0.1/annotator_B01/
data/private/annotations/stage-s-pilot-v0.1/adjudicator_C01/
```

## What this does not authorize

- Stage V verdict labeling
- Treating independent A/B exports as gold
- Model pre-labeling of the 48-pack
- Changing inclusion rules after seeing labels
