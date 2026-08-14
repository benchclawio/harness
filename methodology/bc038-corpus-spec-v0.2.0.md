# bc-038 ground-truth corpus specification

Version: 0.2.0. Frozen 2026-08-14 after the v0.1.0 pilot and before any v0.2.0
evaluation. Governed by `methodology/observability-v0.2.0.md`.

## Why v0.2.0 exists

The v0.1.0 post-run audit found two corpus defects before publication. They make that run
useful as a pilot and invalid as a ranking:

1. Four constructed `format_violation` controls used a restock quantity derived from a
   policy that was not present in the prompt or tool trajectory. A grounded evaluator could
   reasonably fail those outputs. The cases were labelled correct only because the harness
   knew a hidden rule.
2. `wrong_tool_sequence` withheld `price_lookup` from the offered tools. The output used the
   true price, but the agent had no valid path available. That tests unsupported output more
   directly than it tests omission of an available required tool.

No v0.1.0 rate may be used to rank the arms. The raw run stays published as evidence of why
corpus validation belongs after measurement as well as before it.

## Binding repair

The six classes and the 35 matched pairs stay unchanged. Only the information needed to
make two classes identifiable changes:

- Every `format_violation` pair receives an explicit `policy_lookup` result: when stock is
  below the reorder point, replenish to twice the reorder point; otherwise order zero.
  Wrong and correct members share this trajectory. Their only difference remains output
  format.
- Every `wrong_tool_sequence` pair offers both `inventory_lookup` and `price_lookup`. The
  wrong member omits `price_lookup` but reports the true total. The correct member calls it
  and reports the identical total. Task, prompt, tools, contract and final answer are held
  fixed; the trajectory is the variable under test.
- Refund wording is made explicit: exclude the delivery date, and eligibility requires
  fewer than 18 full elapsed days. This removes any inclusive-boundary interpretation.

The v0.2.0 corpus is built deterministically from the preserved v0.1.0 corpus by
`operations/bc038_repair_corpus.py` and hashed before any rerun begins.

## Counts and disclosure

- 35 known-wrong cases and 35 known-correct matched controls.
- Six defect classes: five classes with six pairs and `stale_data` with five.
- Three repeats at temperature zero: 840 measured evaluations across four arms, plus the
  positive-control gates.
- One wrong output is induced. Thirty-four are constructed. The article must say this in
  the results section, not only in limitations.

## Reporting

The statistical unit is the case, not each repeated judgment. The primary false-pass and
false-fail rates use the majority verdict across three repeats for each case and carry
Wilson 95% intervals. Trial-level counts are an audit table only. Verdict flips across the
three repeats are the determinism outcome.

All other requirements in v0.1.0 remain binding: identical arm order, identical criteria,
same judge model, positive controls, per-class rates, raw JSONL publication, and no combined
accuracy score.
