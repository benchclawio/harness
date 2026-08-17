# openai-agents 0.21.1 vs LangGraph 1.2.11 — tool-calling comparison

Evidence for BenchClaw's OpenAI Agents SDK measurement, run 2026-08-17 on `gpt-4o`.
160 scored attempts, 20 per arm per task, four deterministic tasks.

## Result

**Correctness is a tie.** Both arms completed 80/80. The Wilson 95% interval is
`[0.954, 1.000]` for each, so the supported claim is "at least 95.4% completion", not
"100% reliable". Zero failures in either arm, which means the failure taxonomy has no
data from this run.

Paired by `(task_id, run_index)` so provider drift cancels, subject minus control:

| Metric | Subject median | Control median | Delta | Bootstrap 95% | Verdict |
|---|---:|---:|---:|---|---|
| Wall time | 2.450 s | 2.127 s | +0.310 s | `[+0.194, +0.455]` | real, ~15% slower |
| Input tokens | 756 | 703 | +52.5 | `[+33, +72]` | real |
| Output tokens | 60 | 60 | 0 | `[0, 0]` | identical |
| Cost per run | $0.00260 | $0.00253 | +$0.0001 | `[+0.0001, +0.0002]` | real, ~4.6% |

Latency spread runs the other way: subject p95 3.442 s against control p95 3.540 s. The
subject's median is higher but its tail is not.

## The input-token gap is deterministic, not noise

Every bootstrap interval on `tokens_in` is zero-width **within** a task — the same delta on
every single run:

| Task | Input-token delta | Wall-time delta |
|---|---:|---|
| `inventory-reorder` | +18 (exact, every run) | +0.318 s `[+0.191, +0.587]` |
| `recover-stale-revision` | +33 (exact) | +0.257 s `[+0.084, +0.583]` |
| `dependent-shipping-quote` | +72 (exact) | +0.390 s `[+0.110, +0.590]` |
| `refund-policy-minimal-tools` | +78 (exact) | +0.327 s `[-0.008, +0.852]` — crosses zero |

This is tool-schema serialisation overhead, not model variance: the two SDKs describe the
same tools to the same endpoint with a fixed difference in bytes, and the gap grows with the
number and complexity of tools in the task.

The exception is stated plainly: on `refund-policy-minimal-tools` the wall-time interval
crosses zero, so that task alone shows **no measurable latency difference**.

## Pins

- Subject: `openai-agents` 0.21.1 (released 2026-08-16), `openai` 3.1.0, 40 distributions
- Control: `langgraph` 1.2.11 (released 2026-08-11), `langchain-core` 1.5.5, 34 distributions
- Shared: `pydantic` 2.13.4
- Model: `gpt-4o`, temperature 0, `parallel_tool_calls: false`, 440 scored provider requests
- Both arms forced onto **Chat Completions** so they hit the same endpoint
- Task suite SHA-256: `ec72e7440ea177d150ee550ea6dbe908b02410cae6e45f78aefa9eed29f339bf`,
  verified unchanged before warmup
- Order counterbalanced; one attempt per subprocess
- Host: Hetzner cpx11, 2 vCPU / 4 GB, Ubuntu 24.04, Ashburn; destroyed 17:20 UTC same day
- Spend: $0.019 warmup + $0.384820 scored = $0.4038 total

## Limitations

- **One model.** The comparison holds for `gpt-4o` at these four tasks. It is not a general
  claim about either framework.
- **The subject is OpenAI's own SDK, measured on an OpenAI model.** The same-day control and
  this published raw data are the answer to that objection, not a denial of it.
- **`openai-agents` 0.21.1 was one day old** at measurement time.
- **Endpoint forced.** The SDK ships defaulting to the Responses API. As-shipped latency may
  differ from what is measured here.
- **LangGraph 1.2.11 was re-measured from scratch.** These numbers do not lay over BenchClaw's
  published LangGraph 1.2.9 figures from 2026-07-25. Never compare wall times across dates.
- **Zero failures** means the failure taxonomy is empty for this run.

## Two findings from build, not from the scored run

1. **Tracing is on by default in `openai-agents` and uploads to OpenAI.** It posts to
   `api.openai.com/v1/traces/ingest` authenticated with your own API key, and
   `OPENAI_AGENTS_TRACE_INCLUDE_SENSITIVE_DATA` defaults to *true*, so prompts and tool
   payloads go with it. LangGraph uploads nothing by default. Tracing was disabled three ways
   here (`OPENAI_AGENTS_DISABLE_TRACING`, `set_tracing_disabled`, a no-op processor); left on,
   it would have added an unmeasured round trip per run.
2. **The two frameworks classify bad tool arguments differently.** `openai-agents` rejects
   them outright (`malformed_tool_call`); LangGraph coerces the types and fails later at
   scoring (`invalid_final_answer`). Found in fake-mode acceptance tests, not in the scored
   run.

## Contents

| Path | What it is |
|---|---|
| `bc040-scored-raw-2026-08-17.jsonl` | 160 scored attempts, one JSON object per line |
| `bc040-warmup-raw-2026-08-17.jsonl` | 8 warmup attempts, single pass |
| `bc040-analysis-2026-08-17.json` | Per-arm, per-task and paired statistics |
| `bc040-results-2026-08-17.md` | Written analysis |
| `bc040-build-plan-2026-08-17.md` | Design frozen before the run |
| `bc040-static-audit-2026-08-17.md` | Static security audit of the subject package |
| `methodology/bc040-manifest-v0.5.0.json` | Full run manifest and eligibility record |
| `methodology/real-pilot-task-suite-v0.1.0.json` | The four tasks, frozen |
| `methodology/agent-frameworks-v0.1.0.md` | Protocol, published before any framework result |
| `adapters/` | Both workers, shared tools, runner and acceptance tests |
| `locks/` | Exact resolved dependency sets for both environments |
| `scripts/bc040_analyze.py` | Recomputes every number above from the raw JSONL |
| `provenance.json` | Host, pins and artefact hashes |
| `SHA256SUMS` | Checksums for every file in this bundle |

## Reproducing

`scripts/bc040_analyze.py` reads `bc040-scored-raw-2026-08-17.jsonl` and reproduces
`bc040-analysis-2026-08-17.json` byte for byte, using this repository's harness package:

```
cd results/openai-agents-0.21.1-vs-langgraph-1.2.11-2026-08-17
PYTHONPATH=../../src python3 scripts/bc040_analyze.py \
    bc040-scored-raw-2026-08-17.jsonl /tmp/recomputed.json
```

Verified on 2026-08-17: the recomputed output compares equal to the published file. Re-running
the benchmark itself needs an OpenAI API key, the two locked environments and roughly $0.39 of
`gpt-4o` spend.

Evidence was scanned for API keys, bearer tokens, private keys, the server IP and email
addresses before publication: zero hits.
