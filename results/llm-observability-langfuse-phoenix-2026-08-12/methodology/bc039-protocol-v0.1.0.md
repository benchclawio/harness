# bc-039 study protocol

Version: 0.1.0 — frozen 2026-08-12, **before any measurement exists**.

Governing addendum: `methodology/observability-v0.1.0.md` v0.1.0.
Core: `methodology/core-v0.1.0.md`.
Workload suite: `methodology/bc039-workload-v0.1.0.json`,
SHA-256 `423980f8aa741c0c88dd82c1ba5fa0c09a9f25c3a51291e63c51389fd956ca10`,
regenerable byte-for-byte with `python3 operations/bc039_workload.py`.

## Arms

| arm | SDK | deployment |
|---|---|---|
| `control` | none | n/a |
| `langfuse` | `langfuse` | self-hosted, same box |
| `phoenix` | `arize-phoenix` + `openinference-instrumentation-openai` | self-hosted, same box |

**Datadog is out of v1.** It is a commercial SaaS product, and the addendum forbids comparing
self-hosted against SaaS on latency: a network round trip to a vendor region against a local
process is a deployment difference, not a product difference. Including it would either
invalidate the overhead comparison or force a separate arm structure. It earns its own
follow-up with SaaS framing. This is a scope decision, not a finding about Datadog.

Both instrumented arms are configured **the way each project's own documentation prescribes**,
not forced into a common shape. That is the realistic condition, and it means a capture
difference may reflect the recommended integration rather than the backend. Recorded as such.

### Deviation, recorded 2026-08-12 during implementation

The clause above was written before the arms existed. As built, **both arms emit manual spans
and auto-instrumentation is disabled** (`auto_instrument=False` on Phoenix; Langfuse driven
through explicit `start_observation` calls rather than its OpenAI wrapper).

Why the change: with each side's auto-instrumentor active, a capture difference would be
attributable to two different instrumentation libraries reading the OpenAI client, not to the
tools' ingest, storage and read-back. Since capture completeness against a known denominator
is the primary outcome, isolating the backend is the more honest measurement — and the
denominator only holds if both arms emit the same spans.

What this costs: the study no longer says anything about either project's default
auto-instrumentation quality, which is what many readers actually install. That limitation is
stated in the article, and it is a candidate for a follow-up. The clause above is superseded
by this note; it is left in place rather than edited so the change is visible.

## Versions

Pinned at run time and recorded with hashes in the run manifest. Resolved 2026-08-12:

| package | version | released |
|---|---|---|
| `langfuse` | 4.14.4 | 2026-08-11 |
| `arize-phoenix` | 20.1.0 | 2026-08-12 |
| `openinference-instrumentation-openai` | 0.1.54 | 2026-08-07 |

Both primary arms moved inside 48 hours of freezing this protocol. The pin is taken on the
run date and stated in the copy; any later release is out of scope for this study rather than
silently absorbed.

Model: `gpt-4o`, `temperature=0`, parallel tool calls disabled, fixed scenario order.
The model is a nuisance variable here, not the object of study.

## Ground truth, per run

From the frozen suite. These are exact integers known before the run starts.

| signal | per run | per arm (20 runs) |
|---|---|---|
| LLM spans | 10 | 200 |
| tool spans | 7 | 140 |
| retrieval spans | 3 | 60 |
| total spans | 20 | 400 |
| parent-child edges | 9 | 180 |
| injected errors | 2 | 40 |

## Primary outcome: capture completeness

Capture rate per signal type, against the denominators above. **Never averaged into a
composite.** Dropping token counts and dropping tool spans are different failures with
different consequences.

Reported per arm:

- LLM spans captured / issued
- tool spans captured / issued
- retrieval spans captured / issued
- parent-child edges correct / issued (a flat trace is a captured-but-useless trace)
- token counts matching the provider's own reported usage
- cost figures matching a hand computation from OpenAI's published price
- error records captured / injected

## Secondary outcomes

Never the headline:

- added wall-clock latency per request against the `control` arm
- added tokens, if a tool injects anything into prompts
- resident memory delta of the application process with the SDK attached
- time from request completion to the record being queryable through the tool's own API

## Statistics

Capture rate is a **proportion**. Intervals are Wilson score intervals at 95%, not the
bootstrap used for timing differences in bc-025 and bc-045. Using a timing bootstrap on a
proportion would be a category error.

**A 20-run sample cannot distinguish 100% from 99%.** With 400 span opportunities per arm a
perfect result gives a Wilson lower bound near 99.0%, and the copy must say that rather than
implying a perfect score is proven.

Overhead uses the existing bootstrap percentile interval on the difference of means against
`control`, 10,000 resamples, fixed seed. Overlapping intervals are reported as "not
significant" and never as a winner.

## Controls and gates

1. **Uninstrumented control arm is mandatory.** Overhead is the difference against it and
   nothing else.
2. **Positive control gates every arm.** Before the measured window opens, assert the SDK
   initialised and that one known probe span arrived end to end through the tool's own API.
   An arm that fails its positive control does not run. A misconfigured exporter emits zero
   spans, which looks identical to catastrophic data loss and is not — cluster two already
   produced a clean-looking result for a test that never ran.
3. **Flush window: 30 seconds**, declared here in advance and applied identically to every
   arm. Both SDKs batch and export asynchronously; a run that tears down before flush loses
   spans through impatience, not defect. Re-query after the window before recording anything
   as dropped.
4. **Read the API, never the dashboard.** Raw records are exported from each tool's own API
   and counted by us. A screenshot of a vendor's aggregation is the vendor's arithmetic.
5. **Record plan tier, quota and retention per arm.** Both arms are self-hosted here, so
   quota is not expected to bind — but it is recorded, because data missing to an exhausted
   quota is not a capture defect and reporting it as one would be a serious error.
6. **Same-day control.** All arms run interleaved in one session on one host. No timing is
   ever compared against a number measured on another date; API latency drifts materially
   day to day.
7. **Determinism check.** If a scenario's recorded output varies between arms, the workload
   is not adequately controlled and the run is void.

## Run counts

20 instrumented runs per instrumented arm, plus 20 `control` runs. Three arms, 60 runs,
1,200 span opportunities in total, ~600 model requests.

## Reporting rules

- Every dropped span is a finding and is reported **individually**, with what was dropped and
  under what conditions. Aggregate percentages hide the case a reader cares about.
- A null result — all arms capture everything — is a publishable finding, stated as plainly
  as a difference. If that is the outcome, the article rests on the overhead numbers, the
  nesting-correctness result and the completeness table, and says so.
- No composite score. No "winner" unless an interval supports one.
- Referring-domain targets are explicitly not a success metric for this piece
  (`backlink_finding`, 2026-08-09: the page with the most links earns the least traffic).

## Declared limitations, written before the data

- Scripted control flow measures capture of a known agent-shaped workload, not capture of an
  arbitrary framework integration.
- One model, one provider, one host, one deployment mode (self-hosted).
- Six scenarios, 20 spans per run. Long-horizon traces with hundreds of spans are not tested
  and batching behaviour may differ materially at that scale.
- Datadog, LangSmith, Comet Opik, Helicone and Braintrust are not measured.
