# EviReview reuse audit

## Reusable engineering principles

- explicit versioned input/output contracts;
- separation of model-visible artifacts from evaluator-only labels;
- validators that report invalid records rather than silently dropping them;
- exact model/config/run metadata and prompt hashing;
- frozen dataset splits and review-time evidence discipline.

## Not transferred

- the Direct/Context/EviReview prompt comparison;
- the six hand-written C1/C4/C7/E1/E4/E7 tasks;
- their comments, manually reconstructed context, scores, results or conclusions;
- the old evidence taxonomy's `external_specification` field;
- any claim that the previous pilot demonstrates EviScope feasibility.

The old tasks may later be executed only as non-statistical engineering smoke
inputs, under an explicit `synthetic_smoke` marker. They must never be combined
with the natural or challenge sets.

