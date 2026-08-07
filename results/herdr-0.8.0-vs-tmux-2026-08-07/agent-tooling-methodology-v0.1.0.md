# Agent-tooling methodology addendum

Version: 0.1.0

This addendum extends the methodology core for cluster two: **agent tooling** — the
software agents run *inside* rather than the frameworks they are written with. Terminal
multiplexers, session runtimes, process supervisors, sandboxes.

Cluster one measures how well a framework drives a model. Nothing here involves a model at
all, so most of the agent-framework addendum does not apply and its absence must not be
read as an omission.

## Why this cluster needs its own addendum

An agent-framework benchmark is dominated by model non-determinism: the same prompt gives
different completions, so the statistics exist to separate subject effects from sampling
noise. A session-runtime benchmark has the opposite problem. Operations are near
deterministic and take milliseconds, so the noise is the *host* — scheduler, page cache,
neighbouring tenants — and the controls have to target that instead.

Reporting a systems measurement with the framework addendum's apparatus would be
misleading in both directions: confidence intervals implying model-style variation, and no
control at all for the thing that actually varies.

## Primary outcome

There is no single primary outcome. This cluster reports a **vector of independent
operation costs**, each measured separately and never combined into a score:

- CLI invocation cost — one scripted command against a running server;
- session/workspace creation with a live shell;
- command round-trip — send input, poll until output is readable;
- server cold start;
- resident memory at N held sessions;
- session survival across abrupt client loss.

A composite "performance score" across these is forbidden. They trade against each other
and weighting them is an editorial claim disguised as a measurement.

## Controls

- **All arms on one host, in one run, interleaved per metric.** Never compare a number
  taken on one day against a number taken on another. Host latency drifts materially
  between days; the same-day control is what makes the comparison a comparison.
- **Version pinning is a first-class control, and it cuts both ways.** The reviewed tool
  is not the only subject that has a version. A distribution-default comparator can be
  years old, and comparing a current tool against a stale baseline systematically flatters
  the tool under review. Where the default and the current release differ, **run both as
  separate arms.**
- Each arm gets its own server socket and its own process tree. Two versions of the same
  program will otherwise share a server and silently pool their memory.
- Memory is attributed by **PID tree from the arm's own server PID**, never by process
  name. Two builds of the same program have the same process name.
- No network activity, no model calls, no credentials on the box during measurement.
- Identical shell, identical working directory, identical session count per arm.

## Run counts and reporting

- Minimum 20 measurements per arm per metric, matching the core rule. Cold start is
  expensive to sample and is the metric most likely to be under-run; it is not exempt.
- Report mean, standard deviation and a 95% confidence interval for every timing metric.
- **Overlapping intervals are reported as "not significant" and never as a winner** — the
  core rule, restated because the effect sizes here are small in absolute terms and the
  temptation to call a 3 ms gap is strong.
- **Spread is a finding, not an error bar.** A runtime that is faster on average and far
  less predictable is a different product from one that is merely faster, and the standard
  deviation is what says so. Report it in the copy, not only in the table.
- Memory is reported as a two-parameter model — baseline plus marginal cost per session —
  because the two orderings can disagree. Give the crossover point where they do.

## Success and failure

Binary outcomes (survival) require an explicit **validity gate** recorded per repetition.
A repetition that cannot be shown to have exercised the condition under test is recorded
**invalid**, not as a pass. Pass rates are computed over valid repetitions only, and the
invalid count is published alongside.

This exists because of a real defect: bc-045's first survival run attached its client to a
workspace other than the one under test, so every repetition "passed" a test that was
never run. An unscoped validity gate produces a clean-looking result that means nothing.

A null result — arms indistinguishable — is a publishable finding and is reported as
plainly as a difference.

## What this cluster does not measure

State explicitly in every post. For session runtimes this normally includes: real
interactive latency under a live terminal, behaviour over a genuine high-latency SSH link,
multi-user access, plugin ecosystems, and anything requiring a human at a keyboard.

Measuring shell processes is not the same as measuring coding agents. If the post's
subject claims agent-specific benefits, either measure them with a real agent or say we
did not.

## Provenance

Publish for every run: exact versions and how each was obtained (distribution package
versus source build), binary or tarball SHA-256, kernel, CPU model, memory, host class,
and date. A source-built arm and a packaged arm differ in build flags; say which is which.
