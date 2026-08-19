# Gate 0 independent verification — 2026-08-14

## Verdict

**Engineering scaffold: PASS. Overall Gate 0: BLOCKED pending external resource confirmation.**

This review was performed independently against the Gate 0 requirements in the
FSE 2027 implementation plan. A valid schema or a reported server is not treated
as evidence that people, quotas, model access, budget, or a real review-time
snapshot have been confirmed.

## Executed evidence

From the `eviscope/` directory:

```text
python3 scripts/validate.py --all
=> 7 files, 0 issues (including cross-file sample/evidence references)

python3 -m unittest discover -s tests -v
=> 24 tests passed

python3 -m compileall -q src scripts tests
=> exit 0

bash -n scripts/collect_server_env.sh
=> exit 0
```

The tests include malformed JSON and collection types, incomplete provenance,
future-artifact leakage, synthetic-data analysis leakage, missing evidence,
non-progressive evidence levels, false Gate completion, missing mandatory Gate
criteria, unconfirmed personnel, unknown cross-file evidence IDs, server output
privacy fields, and a temporary two-commit Git repository snapshot preflight.

Additional checks:

- every JSON contract/example parses successfully;
- a locally collected server inventory passes validation and contains aggregate
  hardware/tool information without usernames, hostnames, addresses, process
  commands, SSH configuration, or credential values;
- invalid repository/SHA snapshot input exits non-zero;
- snapshot diff inspection disables external diff and text conversion drivers;
- `EviReview` remains clean at commit
  `1a4356a2ab43c00bd4fbeb5a4eeee7fe1feaaf28`;
- no old EviReview task, result, or conclusion was copied into EviScope.

## Defects found and repaired

### P0 — resolved

1. The validator previously accepted a Gate marked `passed` when all criteria
   were marked confirmed but had no evidence. Mandatory criterion IDs, allowed
   states, unique IDs, and evidence for completed criteria are now enforced.
2. Completion states were previously global, so personnel or compute criteria
   could be called `implemented` and make a false `passed` Gate. Completion is
   now criterion-specific: external resources require `confirmed`, while only
   the protocol artifact completes as `implemented`.

### P1 — resolved

1. Dataset records with empty provenance objects previously passed. Required
   repository, PR, commit, license, timestamp, review, path, and artifact
   invariants are now checked.
2. Empty server and experiment records previously passed because their semantic
   validators were no-ops. They are now rejected.
3. The annotation example referenced an undeclared `synthetic-file` artifact.
   The fixture and `--all` cross-file referential-integrity checks now agree.
4. Malformed list/object values could crash validators. Regression tests now
   require issues to be returned instead.
5. Linux CPU and memory collection used commands that could return only headers
   or no model. Collection now reads only the CPU model and aggregate RAM size.
6. Snapshot inspection now explicitly disables repository-configured external
   diff/textconv execution.
7. The README previously left the location of the private resource working copy
   ambiguous. It now directs it to ignored `data/private/` storage.
8. Cross-file validation now rejects claim text/character-span mismatches and
   evidence cited above the judgment's disclosed evidence level. Malformed
   collection fields are skipped only by cross-reference traversal after the
   per-file validator reports them, rather than crashing `--all`.
9. Python boolean values could pass integer-only semantic checks. PR numbers,
   annotation spans, pilot targets and repository counts now reject booleans.
10. Retrieval budget and release-rule fields were present but not semantically
    enforced. Positive budgets and the registered accept/reject/abstain rule
    are now validated.
11. Snapshot preflight now rejects identical or empty commit comparisons and
    converts Git timeouts or execution failures into explicit non-ready output.
9. Snapshot preflight output no longer echoes the local repository path, which
   could otherwise reveal a server account or directory identity when logs are
   shared.

### P2 — open/non-blocking for the scaffold

1. The dependency-free validator mirrors the core JSON contracts and adds
   semantic/cross-file checks, but it is not a complete Draft 2020-12 JSON Schema
   engine. Before artifact release, run the schemas through a pinned `jsonschema`
   or AJV implementation as an additional conformance job.
2. The local workstation inventory has no CPU model string; this does not
   substitute for the required laboratory-server inventory.

## Gate blockers

The following require human or laboratory evidence and must not be inferred:

- independent annotator A confirmed;
- independent annotator B confirmed;
- adjudicator and adjudication commitment confirmed;
- laboratory-server hardware, scheduler/partition, quota, wall-time, storage,
  network policy, and permitted container/runtime workload profiled;
- exact local/API model access and pilot/full budget ceilings confirmed;
- data redistribution owner confirmed;
- one real public PR base/head reconstruction, timestamp, and license smoke test
  completed.

Do not advance to Gate 1 sampling until these are recorded and
`governance/gate0_status.json` can truthfully satisfy its decision rule.
