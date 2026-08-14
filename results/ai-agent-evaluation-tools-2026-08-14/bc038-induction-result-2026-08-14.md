# bc-038 stage 1: induction result

Run: 2026-08-14, 180 runs (60 tasks x 3), `gpt-4o-mini`, temperature 0, cost **$0.015085**.
Raw: `operations/bc038-induction-raw-2026-08-14.jsonl`. All 180 completed; zero unparseable
outputs; zero step-limit stops.

## Headline: induction mostly failed, and that is the result

The workload was designed to make a cheap model fail in six different ways. It did not.

| target class | tasks | distinct defects induced |
|---|---|---|
| `arithmetic_error` | 12 | **0** - every refund case correct, including both 18-day boundary orders |
| `hallucinated_field` | 12 | **0** - never invented the absent field, correctly listed it as missing |
| `stale_data` | 6 | **0** - always called `inventory_refresh` |
| `unsupported_claim` | 12 | 1 genuine (`unsup-09`) + 1 type violation (`unsup-01`) |
| `wrong_tool_sequence` | 12 | 1 pattern, 8 instances - **and not the intended defect** |
| `format_violation` | 6 | 1 pattern, 4 instances - **and not the intended defect** |

**Four distinct defects, not six classes of six independent cases.** The corpus spec's
minimum is not met, so under our own frozen rules the evaluator arms cannot be ranked on
this corpus. That rule exists precisely to stop us doing what we would otherwise be tempted
to do here.

## What actually went wrong, per class

**`wrong_tool_sequence` did not induce.** The intent was that, with `price_lookup` withheld,
the model would guess a unit price and return a fabricated total. **It never fabricated a
price.** `total_usd` is `null` in all 36 runs. What it did instead is return
`unavailable: false` alongside that null total - a self-contradictory output. That is a real
defect and a useful one, but it belongs to contract coherence, not tool sequencing. The
class we most wanted to measure is the class we did not get.

**`format_violation` induced an arithmetic error instead.** Four SKUs came back with the
wrong `restock_quantity`, and the cause is identical in all four: the model restocked *to*
the reorder point rather than to twice it, ignoring half the policy sentence. BCL-204 gave
`10 - 7 = 3` where the policy gives `20 - 7 = 13`; BCL-450 `12 - 3 = 9` against `24 - 3 = 21`;
BCL-512 `20 - 19 = 1` against `40 - 19 = 21`; BCL-677 `8 - 0 = 8` against `16 - 0 = 16`.

One misreading, four SKUs. **By the spec's own independence rule that is one defect, not
four**, which is the exact failure mode the feasibility doc rejected the old corpus for. It
would have been very easy to count it as four.

**`unsupported_claim` produced one genuinely good case.** `unsup-09` asked which region is
the default for new projects. The documentation says only that the service *runs in*
eu-central and us-east. The model answered `eu-central` with
`supported_by_documentation: true`. Confident, plausible, unentailed - textbook class 4.
`unsup-01` returned the string `"null"` rather than JSON `null`, which is a type violation
rather than an unsupported claim.

## Secondary finding: temperature 0 is not deterministic

**7 of 60 tasks did not return identical output across their three runs.** Two are
substantive: `seq-02` and `seq-06` flipped `unavailable` between `true` and `false` between
runs, on the same prompt, same tools, same model, temperature 0. The other five differ only
in free-text `reason` wording.

This matters beyond bc-038. It means a single-run evaluation of an agent is not reproducible
even with the sampling knob turned off, and it is worth stating in the article regardless of
what happens to the corpus.

## Why the induction failed

The tasks were calibrated against a defect `gpt-4o-mini` made in July 2026 on
`refund-policy-minimal-tools`. It no longer makes it: all 36 refund runs here are correct,
including the two orders sitting exactly on the 18-day boundary that produced the original
failure. Either the model behind that alias has moved, or the original task's under-tooling
was doing more work than its arithmetic. We did not run a controlled comparison, so this is
an observation, not a claim.

## Options

1. **Construct the missing classes and disclose per class.** The corpus spec already permits
   this and requires the disclosure. Cheap - no further model spend - but the corpus becomes
   majority-constructed, which weakens the headline from "real agent failures" to "outputs
   with known defects". The evaluator measurement survives intact, because what is being
   measured is the *judge*, not the agent.
2. **Amend the workload to v0.2.0 and re-induce with harder tasks.** Keeps the corpus real.
   Costs another induction run and, on this evidence, is not certain to work.
3. **Park bc-038** and write up the induction failure plus the temperature-0 result as a
   smaller piece.

Recommended: **1**, with the constructed classes named in the copy and in the bundle. The
article's claim is about evaluators, and a constructed defect with a known label tests a
judge exactly as well as an induced one - provided we never imply the inputs were organic.
