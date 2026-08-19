# Venue lock: SANER 2027 Agentic AI4SE

Status: **superseded** — restored to FSE 2027 on 2026-08-19. See
`governance/venue_lock_fse_2027_2026-08-19.md`.

## Locked target

- Venue: IEEE SANER 2027
- Track: Agentic AI4SE Track
- Abstract (mandatory): 2026-10-19 AoE
- Paper: 2026-10-23 AoE
- Notifications: 2026-12-08
- Camera ready / author registration: 2027-01-08
- Format: IEEE, ≤10 pages + ≤2 reference pages
- Review: double-anonymous
- Proceedings: IEEE Digital Library as part of SANER 2027
- Official CFP: https://conf.researchr.org/track/saner-2027/saner-2027-agentic-ai4se-track

## Paper object (must match track Relevance)

Working object for this venue:

> A budget-constrained evidence-escalation **agent** for review-time verification of atomic claims in code-review comments.

The system must be evaluable as an agentic SE system: state, tool use, retrieval/escalation actions, stop/abstain under correctness and cost constraints. It is **not** a multi-agent reviewer generator and **not** an isolated single-shot model call wrapped in agentic wording.

Primary evaluation story: reduce false rejection of beyond-diff `SUPPORTED` claims versus diff-only and unconstrained retrieval/full-context agents, without materially increasing false acceptance, under matched budgets.

## Explicitly not the default path anymore

- FSE 2027 Research Papers is no longer the planning default.
- SANER Research Track (2026-09-25) is not the planning default.
- SANER ERA / Short Papers / RENE are **not** planned fallback venues under this lock.

## Allowed responses to failure

If scientific or staffing gates fail, the project may:

1. stop the SANER Agentic sprint; or
2. shrink claims (for example drop prevalence, drop L*, reduce language scope) **while remaining on SANER Agentic**; or
3. defer the work to a later cycle after SANER 2027.

The project must **not** treat ERA/Short as an automatic downgrade path under this lock.

## Scientific stop conditions (not venue downgrades)

Any of the following blocks a credible Agentic submission and requires stop or claim shrink, not venue shopping:

1. No third-person adjudicator for formal Stage S / Stage V.
2. Oracle evidence does not improve the judge over diff-only on the frozen gold subset.
3. Beyond-diff `SUPPORTED` claims are too rare to support the agent story after honest attrition reporting.
4. The agent loop cannot invoke review-time tools and stop under budget with audited traces.
5. Review-time leakage cannot be controlled.

## Immediate execution priorities under this lock

1. ~~Confirm A/B/C schedule for formal Stage S on the hashed 48-pack.~~ **Done 2026-08-19:** B and C available now; formal Stage S authorized in `governance/stage_s_pilot_authorization_2026-08-19.md`.
2. Build the minimal agent loop in parallel: observe claim → choose tool → update evidence state → decide or escalate/stop.
3. Build L1 (and then L2/L3 as needed) review-time evidence packages for adjudicated MATERIAL claims only.
4. Produce Stage V gold on a usable subset before expanding sample size.
5. Run paired baselines on the same frozen claims: diff-only, token-matched full-context, unconstrained tool/RAG agent, EviScope stop policy.
6. Keep double-anonymous and Data Availability constraints in mind from day one; restore or initialize git provenance.

## Codename note

Historical directory `eviscope-fse2027/` retains its name for continuity. Venue authority for planning is this lock file plus updated `00_scope.md` and `state.json`.
