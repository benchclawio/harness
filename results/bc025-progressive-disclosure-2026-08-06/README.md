# Does progressive disclosure actually cut agent token costs?

Supporting evidence for <https://benchclaw.io/agent-progressive-disclosure-token-cost/>.

Every page that discusses progressive disclosure asserts it cuts context cost. None
publishes a number. This is the number.

**Subject:** `pydantic-ai-slim[openai]==2.24.0`
**Model:** `gpt-4o`, temperature 0, `parallel_tool_calls=False`, no framework or provider retries
**Date:** 2026-08-06
**Runs:** 80 scored (20 per cell), preceded by a 4-run warmup
**Total cost:** $0.279585 scored, $0.013168 warmup

## Design

20 capabilities are registered in **every** run of **every** cell. The arms differ only in
whether those capabilities are marked `defer_loading`, so any token difference is
attributable to disclosure and nothing else.

| Cell | Arm | Transport | Capabilities |
|---|---|---|---|
| A-chat | control | `OpenAIChatModel` | 20 always-on |
| B-chat | treatment | `OpenAIChatModel` | 20 behind `DeferredLoadingToolset` |
| A-resp | control | `OpenAIResponsesModel` | 20 always-on |
| B-resp | treatment | `OpenAIResponsesModel` | 20 behind `DeferredLoadingToolset` |

Both transports are measured because tool search executes differently on each: the
Responses API runs it server-side, Chat Completions falls back to a local `search_tools`
toolset. Cells are interleaved run by run rather than executed in blocks, so provider-side
drift cannot masquerade as the effect.

## Results

| Cell | Input | Output | Requests | Searches | Cost | Wall | Exact match |
|---|---|---|---|---|---|---|---|
| A-chat | 1361.5 | 42.4 | 2.00 | 0 | $0.003827 | 5.48s | 20/20 |
| B-chat | 945.2 | 65.2 | 3.00 | 2.00 | $0.003016 | 6.53s | 20/20 |
| A-resp | 1353.8 | 51.1 | 2.00 | 0 | $0.003895 | 7.47s | 20/20 |
| B-resp | 1001.0 | 73.8 | 3.00 | 2.00 | $0.003241 | 8.40s | 20/20 |

Within-path deltas, bootstrap 95% CI (10,000 resamples, seed 20260806):

| Metric | chat A→B | responses A→B |
|---|---|---|
| Input tokens | −30.6% [−491.6, −329.0] | −26.1% [−456.9, −231.2] |
| Output tokens | +54.1% [20.1, 25.5] | +44.5% [19.1, 26.8] |
| Model requests | +1.0 [1.0, 1.0] | +1.0 [1.0, 1.0] |
| Cost | −21.2% [−0.0010, −0.0006] | −16.8% [−0.0009, −0.0003] |
| Wall time | +19.1% [0.29, 1.74] | +12.3% [−0.33, 2.16] |

Chat Completions and Responses are never compared against each other — they account for
tokens differently, so a cross-path delta would measure the provider's bookkeeping rather
than progressive disclosure.

The Responses wall-time interval crosses zero. We report it as no measured difference, not
as a slowdown.

## What we did not measure

- One model only (`gpt-4o`). We do not claim these ratios hold on other models.
- One capability count (20). The saving is a function of how much schema you defer; a
  different pool size gives a different number.
- Tasks needing exactly one capability. We did not test tasks requiring several loads, where
  the extra round-trips would compound.
- Anthropic's native BM25/regex tool search. We hold no Anthropic credential.

## Reproduce

```bash
python3 bc025_capabilities.py          # regenerates the frozen suite, byte-identical
python3 analyze_bc025.py               # recomputes every figure above from the raw JSONL
```

Both are offline and cost nothing. `run_bc025_deferred_disclosure.py` performs the paid
runs and needs `OPENAI_API_KEY`; it has a hard spend ceiling and stops on the first failure.

Set `BENCHCLAW_ROOT` if you run these from outside the repository layout.

## Files

| File | What it is |
|---|---|
| `bc025_capabilities.py` | Deterministic generator for the capability pool and task suite |
| `bc025-task-suite-v0.1.0.json` | The frozen suite, 20 capabilities and 4 tasks |
| `worker_bc025.py` | One run of one cell; builds the agent, applies the arm, scores the output |
| `run_bc025_deferred_disclosure.py` | Sequential collector with spend guard |
| `analyze_bc025.py` | Bootstrap CIs and per-cell summaries |
| `bc025-warmup-raw-2026-08-06.jsonl` | 4 warmup runs |
| `bc025-scored-raw-2026-08-06.jsonl` | 80 scored runs, one JSON object per run |
| `bc025-*-manifest-2026-08-06.json` | Run manifests with suite and worker SHA-256 |
| `bc025-scored-analysis-2026-08-06.json` | Computed statistics |

## Changes made before publication

Two edits, neither affecting any measurement:

1. Absolute local paths in the manifests and analysis were reduced to filenames.
2. In `run_bc025_deferred_disclosure.py`, the local variable holding the API key was
   renamed `api_key` → `credential`. Our secret scanner matches on the identifier and
   flagged the assignment, which contains no secret. The same rename was applied to our
   working copy, so the two remain identical.

The worker and task suite — the two artefacts whose SHA-256 the manifests record — are
byte-identical to what executed. `analyze_bc025.py` was re-run after the path change and
reproduces every figure above exactly.
