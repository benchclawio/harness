# Observability and evaluation tooling methodology addendum

Version: 0.2.0. Supersedes v0.1.0, which remains valid for capture-completeness runs
(bc-039 was measured under it and is unaffected).

Frozen **2026-08-14, before any bc-038 measurement exists**, so the protocol-before-results
ordering is verifiable from repository history. Nothing has been installed and no run has
been executed at the time this file is committed.

## What changed and why

v0.1.0 defines one primary outcome for this cluster: **capture completeness**, whether the
instrument records what the application did. bc-039 measured exactly that for Langfuse and
Phoenix and returned a null result.

That outcome does not fit the second half of the cluster. An **evaluation** tool is not
asked to record the truth; it is asked to *judge* it. A tool can capture every span
perfectly and still tell you a wrong answer was correct, which is the failure that costs
somebody money. v0.2.0 adds a second primary outcome for that subclass and leaves the first
untouched.

Pick the outcome by what the tool claims:

| tool claims | primary outcome | version |
|---|---|---|
| it records what happened | capture completeness | v0.1.0, unchanged |
| it judges whether output was correct | **evaluator agreement** | v0.2.0, below |

A tool that claims both is measured on both, reported separately, and never averaged.

## Primary outcome: evaluator agreement with ground truth

The primary outcome is agreement between the tool's verdict and a label we own, reported as
**two independent rates that are never combined into an accuracy figure**:

- **False-pass rate** - known-wrong outputs the evaluator marked correct. The headline.
  This is the failure with real-world cost, and it is the number no vendor publishes.
- **False-fail rate** - known-correct outputs the evaluator marked wrong. The cost of noise:
  an evaluator nobody trusts gets switched off.

Each is a proportion and carries a **Wilson 95% interval**. A single "accuracy" number is
forbidden for the same reason a composite observability score is: the two errors have
different consequences and a class-imbalanced corpus makes the composite meaningless.

**Report per defect class as well as overall.** An evaluator that catches arithmetic errors
and misses unsupported claims is a different product from one with the same headline rate
spread evenly, and the reader is choosing between those two.

### The corpus is the experiment

The measurement is only as good as the labels, so the corpus rules are binding:

- **Ground truth is established before any evaluator sees the data**, recorded in a file
  committed ahead of the run, and each label is hand-verified by a human reading the output
  against the task's expected answer. An automated scorer may propose labels; it may not be
  the sole authority, because the automated scorer is the same class of artefact as the
  thing under test.
- **Defect classes must be independent, not one defect resampled.** Ten runs of one task
  failing one way is an effective denominator near one, whatever the arithmetic says.
  State the number of *distinct* defects alongside the number of cases, always.
- **Minimum six distinct defect classes**, each represented by at least five independent
  cases, and at least as many known-correct cases as known-wrong. Below that, report the
  interval and decline to rank the arms.
- **Prefer real model outputs.** Where a defect must be constructed rather than induced, the
  construction is disclosed per class in the published corpus, and the copy states which
  classes were induced and which were built.
- **Publish the corpus with its labels** in the evidence bundle. A false-pass rate whose
  inputs are not published is exactly the unfalsifiable claim this project exists to reject.

### Mandatory control arm

**A naive judge is a required arm, not an optional extra.** One hand-written prompt, the
same model, no framework, no library. Its purpose is to establish whether the frameworks add
anything a competent engineer could not write in an afternoon.

If a framework does not beat the naive baseline outside the confidence interval, that is
reported in the copy as plainly as a win would be, and it is reported in the summary, not
buried in a limitations section.

## Secondary outcomes

Reported, never as the headline:

- **Induced model cost per evaluation**, per v0.1.0's cost rule. LLM-as-judge spends real
  money attributable to the tool, and it is routinely omitted from vendor comparisons.
- Wall time per evaluation.
- **Verdict inspectability** - whether the tool returns a reason, a score, or a bare boolean.
  Recorded as an observed property, not scored.
- Determinism: the same input evaluated repeatedly, at `temperature=0`, with the number of
  verdict flips reported. An evaluator that disagrees with itself is a finding.

## Controls and provenance

Everything in v0.1.0 continues to apply, with these additions:

- **Judge model is pinned and disclosed**, and is the same for every arm including the naive
  control. Comparing a framework on one judge model against another on a different judge
  model measures the model, not the framework - the exact error bc-004 was built to expose.
- **Run every arm against the identical corpus in the identical order.**
- **A positive control gates the run**: before the measured window, assert each evaluator
  returns the expected verdict on one trivially-correct and one trivially-wrong case. An
  evaluator that is misconfigured returns a uniform verdict, which is indistinguishable from
  a 100% false-pass rate and is not the same thing.
- Record: library name and exact version, judge model ID and temperature, prompt or metric
  identifier used, corpus hash, date, and whether the integration path was the library's
  default or a custom metric.

## What this subclass does not measure

State explicitly in every post: dataset management, CI integration ergonomics, regression
gating workflow, dashboards, team features, and any claim about a tool's performance on
defect classes outside the published corpus. We measure whether the judge is right about
outputs whose truth we know, and what that costs.
