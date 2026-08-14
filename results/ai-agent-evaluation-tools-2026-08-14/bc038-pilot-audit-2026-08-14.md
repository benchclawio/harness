# bc-038 v0.1.0 pilot audit

Status: **invalid for arm ranking; retained as pilot evidence**.

The run completed 840/840 evaluations with zero execution errors. All four positive
controls passed, the downloaded files match the server hashes, and the CX23 was destroyed.
The execution succeeded. The corpus did not.

## Blocking findings

### Hidden restock policy

Four constructed correct controls in `format_violation` report quantities based on
"replenish to twice the reorder point". That rule is present in the harness reference
function but absent from the prompt and trajectory shown to evaluators.

The effect is material, not theoretical. At the case-majority level, the arms false-failed
between zero and five of the six matched format controls. Several reasons explicitly
derived a different, reasonable restock quantity from the visible evidence. Those verdicts
cannot be called evaluator errors when the controlling rule was hidden.

### The trajectory class did not vary a callable trajectory

The v0.1.0 `wrong_tool_sequence` tasks did not offer `price_lookup`. The constructed output
used the true price, but there was no valid tool path available to the agent. The repair
offers the lookup to both members, omits it only from the wrong trajectory, and holds the
final answer fixed across the pair.

### Reporting unit needed to be explicit

Three temperature-zero repeats of one case are repeated measurements, not three independent
defects. The v0.2.0 primary rate therefore uses one majority verdict per case. Trial-level
105-judgment rates remain available as an audit count but are not the headline interval.

## Pilot numbers, not publishable rankings

The preserved analysis is `operations/bc038-analysis-2026-08-14.json`. Its case-level
majority rates are useful only for validating the analysis code:

| arm | false pass | false fail | verdict-flip cases |
|---|---:|---:|---:|
| naive | 6/35 | 11/35 | 8/70 |
| Phoenix | 4/35 | 5/35 | 8/70 |
| DeepEval | 7/35 | 1/35 | 4/70 |
| Opik | 0/35 | 10/35 | 3/70 |

They must not appear in the article as comparative results.

## Secondary provenance gaps to fix in the rerun

- Only the naive arm exposed exact token usage and cost (`$0.1601775`). The three framework
  integrations returned no usage, so their pilot cost is unknown rather than zero.
- The runner recorded the `gpt-4o` alias but not the resolved response model.
- The server environment freeze was not retrieved before teardown.

The rerun must record request/response usage and resolved model through a local request
ledger, save each isolated environment freeze, and treat unavailable usage as a failed
secondary measurement rather than `$0`.
