# Evidence package roles — gold vs automated targeting

Status: **registered engineering rule**  
Date: 2026-08-19  
Does not amend `governance/annotation_guide_v0.3.md` claim text, Stage-S blinding, or Stage-V progressive stop.

This note freezes a construct split that appeared during oracle-escalation smoke. It is not gold and does not authorize changing annotator packets.

## Two packages

| Role | Who sees it | Contents | Used for |
|---|---|---|---|
| **Nested gold package** | Stage-V annotators; reverse-verification (guide §5: ≥20% of verdict records from the **complete** package) | Full L0⊂L1⊂L2⊂L3 artifacts built for that comment | Human `L*`, 三态 gold, disagreement codes |
| **Path-constrained method package** | Automated EviScope verifier (`src/eviscope_verifier.py`) | Same nested builders, then `constrain_package`: keep L0 plus artifacts whose locator matches `.py` paths named in `normalized_text`; off-path decisive citations coerced to `INSUFFICIENT` | RQ3 method P only |

If the claim names no `.py` path, the method package equals the nested gold package at that level.

## What this is not

- Not a change to Stage-S inputs (still comment text only).
- Not a license to filter packages shown to A/B/C.
- Not a fix for the 30B judge emitting `CONTRADICTED` on a matching `hookspec.py` artifact; that remains a judge-capacity limit.
- Not a success-threshold change on the three oracle smoke claims.

## Reporting rule

Human `minimum_evidence_level` is defined only on nested gold packages. Do not report method stop-level as human `L*`. When comparing P to B0/B3/B4, state that P may drop off-path files after retrieval; token-matched full-context baselines must not silently inherit that filter unless a later protocol says so.
