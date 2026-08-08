# Observability and evaluation tooling methodology addendum

Version: 0.1.0

This addendum extends the methodology core for cluster three: **observability and
evaluation tooling** — the platforms that instrument an LLM application and report on it.
Langfuse, Arize Phoenix, Datadog LLM Observability, Comet Opik, LangSmith, Helicone,
Braintrust, and self-hosted OpenTelemetry pipelines.

Cluster one measures how well a framework drives a model. Cluster two measures the
software an agent runs inside. This cluster measures **an instrument**, and that changes
what a benchmark can honestly claim.

## Why this cluster needs its own addendum

The subject under test is the thing doing the observing. Two consequences follow, and
neither is handled by the existing addenda.

**The instrument perturbs the measurement.** Attaching an SDK adds latency, allocations
and sometimes tokens to the workload it is recording. Any overhead figure is meaningless
without an uninstrumented control arm running the identical workload.

**Speed is not the primary question.** A tracing platform that is 5 ms faster and drops
one span in fifty is worse than a slower one that drops none. The reader's actual question
is "will it capture what I need when something goes wrong", which is a **completeness**
measurement, not a performance one. Leading with latency would answer a question nobody
asked.

## Primary outcome: capture completeness

The primary outcome is **capture rate against a known ground truth**, reported per signal
type and never averaged into one figure:

- LLM call spans captured / issued
- tool call spans captured / issued
- retrieval spans captured / issued
- parent-child nesting correct / total spans (a flat trace is a captured-but-useless trace)
- token counts matching the provider's own reported usage
- cost figures matching a hand computation from the provider's published price
- error and exception records captured / injected

We can construct exact ground truth here, which is unusual and is the reason this cluster
is worth measuring at all. We control the workload: the harness knows precisely how many
model calls, tool calls and retrieval steps it issued, in what order and in what nesting.
Every one of those numbers is a denominator we own rather than a vendor claim we repeat.

A composite "observability score" is forbidden, for the same reason it is forbidden in
cluster two. Dropping token counts and dropping tool spans are different failures with
different consequences.

## Secondary outcomes

Reported, but never as the headline:

- added wall-clock latency per instrumented request, against the uninstrumented control
- added tokens, if the tool injects anything into prompts
- resident memory delta of the application process with the SDK attached
- time from request completion to data being queryable through the tool's own API

## Controls

- **An uninstrumented control arm is mandatory.** Identical workload, identical model,
  identical seed and task order, no SDK attached. Overhead is the difference against this
  arm and nothing else. Without it, an overhead number is an unfalsifiable assertion.
- **A positive control gates every run.** Before the measured window opens, assert the SDK
  initialised and at least one known span arrived end to end. A misconfigured exporter
  produces zero spans, which looks identical to catastrophic data loss and is not.
  Cluster two taught this the expensive way: an unscoped validity gate produced a
  clean-looking result for a test that never ran.
- **Define and publish a flush window.** Most SDKs batch and export asynchronously. A run
  that tears down before flush loses spans through impatience, not defect. Fix an explicit
  settle period, apply it identically to every arm, and state it in the copy. Re-query
  after the window before recording anything as dropped.
- **Read the tool's API, never its dashboard.** A screenshot of a vendor's own aggregation
  is the vendor's arithmetic, not our measurement. Export the raw records and count them
  ourselves.
- **Record plan tier, quota and retention state for every arm.** Data missing because a
  free-tier quota was exhausted is not a capture defect, and reporting it as one would be
  a serious error.
- **Do not compare self-hosted against SaaS on latency.** A network round trip to a vendor
  region against a local process is a deployment difference, not a product difference.
  Either separate the arms or state plainly that the comparison is not made.
- Model non-determinism is a nuisance variable here, not the object of study. Pin the
  model, `temperature=0`, fixed task set and fixed order, and record the model as part of
  provenance. If a task's output varies between arms, the workload is not adequately
  controlled and the run is invalid.

## Run counts and reporting

- Minimum 20 instrumented runs per arm, matching the core rule, plus 20 uninstrumented
  control runs for the overhead comparison.
- Capture rate is a proportion: report it with a 95% confidence interval computed for
  proportions, not the interval used for timings. A 20-run sample cannot distinguish 100%
  from 99%, and the copy must say so rather than implying a perfect score is proven.
- Report overhead as mean, standard deviation and 95% CI against the control arm.
  Overlapping intervals are reported as "not significant" and never as a winner.
- **Any dropped span is a finding and is reported individually**, with what was dropped and
  under what conditions. Aggregate percentages hide the case a reader cares about.
- A null result — all arms capture everything — is a publishable finding and is stated as
  plainly as a difference.

## Cost

Two independent figures, never combined:

1. **Platform cost** — what the tool charges for the volume measured, from its live
   published pricing on the date of the run.
2. **Induced model cost** — tokens the tool causes to be spent, most obviously by
   LLM-as-judge evaluations. This is real money attributable to the tool and is routinely
   omitted from vendor comparisons.

Both are disclosed with the total benchmark cost, per the core rule.

## What this cluster does not measure

State explicitly in every post. Normally this includes: dashboard and UI quality, alerting
and on-call ergonomics, RBAC and access control, data residency and compliance posture,
support responsiveness, pricing at volumes we did not run, and long-run retention
behaviour.

We measure whether the instrument records the truth and what it costs to attach. We do not
measure whether an engineer enjoys using it, and we will not imply that we did.

## Provenance

Publish for every run: SDK name and exact version, platform region or self-hosted build,
application framework and version, model ID and temperature, task suite and its hash, flush
window, plan tier, host class, and date. Where an SDK auto-instruments a framework, record
which integration path was used — auto-instrumentation and manual spans are different
products in practice and produce different capture rates.
