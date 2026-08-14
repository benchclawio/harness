# bc-038 ground-truth corpus specification

Version: 0.1.0. Frozen 2026-08-14, before any corpus exists and before any evaluator is
installed. Governed by `methodology/observability-v0.2.0.md`.

## Why this file exists separately

Under v0.2.0 the corpus *is* the experiment. Freezing the evaluator arms while leaving the
corpus to be assembled as we go would let the corpus drift toward whatever the arms happen
to catch. The defect classes, the counts and the labelling procedure are therefore fixed
here, ahead of the induction run.

## Relationship to the existing failure taxonomy

`failure-taxonomy-v1.0.0.md` classifies **execution** failures - how a run broke. Every case
in this corpus is, in those terms, a single class: `invalid_final_answer`. Execution
succeeded, no exception was raised, no budget was hit, and the answer was wrong anyway.

This spec explodes that one bucket along an orthogonal axis: **what kind of wrong**. The two
taxonomies compose; neither replaces the other.

## Defect classes

Six classes, chosen because each defeats a different evaluator strategy. An exact-match
scorer catches 1 and 6 and nothing else; a trajectory evaluator catches 2 and 5; only a
grounded judge has any chance at 3 and 4.

| # | class | definition | why it is hard |
|---|---|---|---|
| 1 | `arithmetic_error` | Correct tools, correct data, wrong computation on it | Output is well-formed and confident. Our real `refund-policy-minimal-tools` failure is this class |
| 2 | `wrong_tool_sequence` | Correct final answer reached by an invalid path - a required lookup skipped and the value guessed | The answer is **right**. Only trajectory-aware evaluation can see it, and a final-answer judge scores it as a pass |
| 3 | `hallucinated_field` | Output contains a field or value present in no tool result | Requires the evaluator to check output against retrieved context, not against plausibility |
| 4 | `unsupported_claim` | Conclusion is plausible and consistent but not entailed by the retrieved data | The hardest class, and the one vendor demos avoid |
| 5 | `stale_data` | A cached or superseded value used where a refresh was required | Values are real and internally consistent, just from the wrong point in time |
| 6 | `format_violation` | Correct content, violates the declared output contract - wrong keys, wrong types, wrapped in prose | Trivial for a schema check, and a grounded judge may forgive it. Included to expose evaluators that conflate "correct" with "usable" |

Class 2 is the load-bearing one. It is the case where the *answer is correct* and the run is
still defective, so an evaluator that only reads the final answer must score it a pass. Any
tool claiming "agent evaluation" rather than "output evaluation" should catch it, and that
claim is on most of the pages ranking for this term.

## Counts

Per v0.2.0's minimum, exceeded deliberately so the per-class intervals are not useless:

- **6 defect classes x 6 independent cases = 36 known-wrong cases.** Independent means six
  different task instances, not one task run six times.
- **36 known-correct cases**, balanced 1:1 so neither a permissive nor a strict evaluator
  gets a free score. These come from the **same induction run**: the workload generates 60
  task instances and the model will answer many of them correctly, so correct cases are
  harvested rather than written separately. This matters - a correct case drawn from the
  same distribution as the wrong ones is a fair test, whereas a hand-written correct case
  would be easier than the defects by construction and would flatter every arm.
- **72 cases total**, each evaluated by 4 arms = 288 evaluations per repeat.
- **3 repeats** at `temperature=0` for the determinism secondary outcome: **864 evaluations**.

## How each class is produced

Option C, as approved by Neo on 2026-08-14: induce from real runs where possible, construct
only where induction cannot reach, and disclose which is which per class.

| class | method | note |
|---|---|---|
| 1 `arithmetic_error` | **induced** | `gpt-4o-mini` produces these reliably; we already have one confirmed instance |
| 2 `wrong_tool_sequence` | **induced** | Under-tool the task and let the model guess the missing value |
| 3 `hallucinated_field` | **induced** | Ask for a field the tools do not return |
| 4 `unsupported_claim` | **induced** | Retrieval task where the corpus is deliberately silent on the question asked |
| 5 `stale_data` | **constructed** | Requires controlling what the tool returns over time; induction is not reliably repeatable |
| 6 `format_violation` | **constructed** | Induction is possible but wasteful when the defect is defined by the contract |

Induction runs on `gpt-4o-mini`, which is the model whose limits we have already
characterised. Any case the induction run does not produce is **not** back-filled by
construction without recording the substitution in the published corpus.

## Labelling procedure

1. The induction run writes raw JSONL exactly as any scored run does.
2. Every output is read by a human against the task's expected answer and assigned a label
   and a defect class. The automated scorer's verdict is recorded alongside but is **not**
   the authority - it is the same class of artefact as the tools under test.
3. Cases where the correct label is genuinely arguable are **discarded, not resolved**. A
   corpus that requires a judgement call is not ground truth, and keeping the awkward ones
   would quietly convert this into a measurement of our own opinion.
4. Discards are counted and the count is published.
5. The finished corpus is hashed and the hash committed **before** any evaluator runs.

## Positive control

Two cases outside the 72, run against every arm before the measured window opens:

- one trivially correct output, which must be marked pass
- one trivially wrong output, which must be marked fail

An arm failing either gate does not enter the run, and the failure is reported. A
misconfigured evaluator returns a uniform verdict, which looks identical to a 100%
false-pass rate and is a completely different finding.

## What is still open

The task instances themselves are not in this file. They are written next, frozen as
`methodology/bc038-workload-v0.1.0.json` with a SHA-256, and committed before the induction
run - the same ordering bc-039 used.
