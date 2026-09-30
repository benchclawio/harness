# When is a trace ready to score? MLflow 3.16.1, DeepEval 4.2.7, Phoenix evals 3.9.0 (source inspection)

Evidence for the BenchClaw article "Running Evals on Traces" (bc-099). Run date: 2026-09-30.

This is a **source inspection**, not a model benchmark. No LLM was called, no tracing server was run, and no number here is a performance figure. The script reads the shipped code of three wheels, prints the relevant lines with line numbers, and runs MLflow's own `calculate_time_window` on a **fake clock** with inputs we chose (a 60 s poll interval, which is our assumption, and the trace durations in the table).

## Inputs (hash-verified by the script)

| Package | Version | Released | Wheel SHA-256 |
|---|---|---|---|
| `mlflow` | 3.16.1 | 2026-09-16 | `e4dfe69ceae31dfc7b8480e76ffe6a7f36752bdfac30e058e6430ade1fb5920b` |
| `deepeval` | 4.2.7 | 2026-09-29 | `8e325bac5a63cd90264a69ab91dd9ea0376f045d16b820193139dd56da2886bd` |
| `arize-phoenix-evals` | 3.9.0 | 2026-09-21 | `425b70bcd2d87cd85a30d812adb9ddbb4b434e51de75795b67d8a4f7d20e76cd` |

All three were the latest releases on PyPI on 2026-09-30.

## Run it

```
python3 inspect_trace_evals.py mlflow-3.16.1-py3-none-any.whl deepeval-4.2.7-py3-none-any.whl arize_phoenix_evals-3.9.0-py3-none-any.whl
```

Standard library only (Python 3.14.4 used). The script aborts if any wheel hash differs. It extracts `calculate_time_window` from the MLflow wheel with `ast` and executes it with stand-in objects; the checkpoint-boundary filter is re-typed from `trace_processor.py` lines 195 to 203 and labelled as such in the output.

## Files

| File | SHA-256 |
|---|---|
| `inspect_trace_evals.py` | `ee2916de96fb694cfb8077207c5f0d68f303b5a2e5fed1dc5a68a3a9c6da82a9` |
| `inspect-output-2026-09-30.txt` | `2b4e5c0f48ebfc88e69ffad9105a36efdd952d7b91880605a859f5a462239860` |

The script was executed three times on 2026-09-30; the three outputs were byte-identical.

## What it shows

1. MLflow online trace scoring picks traces by start time. The window's upper bound is now minus a buffer (default 300 s). No file under `mlflow/genai/scorers/online/` references trace status.
2. On the fake clock, traces that run 60, 240 and 300 s are complete when first scored at +300 s; traces that run 360, 600 and 1,800 s are still in progress.
3. After scoring, the checkpoint moves to the latest scored trace's start time and trace ID, and the boundary filter excludes traces at or below it, so a trace is not selected again.
4. Lookback is capped at 1 hour and a job at 500 traces. After a 3-hour outage the next window starts 6,900 s after the checkpoint, so traces that started in the gap fall outside every later window.
5. DeepEval's in-process path stamps `end_time` on a live trace; its offline `evaluate_trace` only posts a trace UUID and metric-collection name to Confident AI, with no buffer or inactivity logic in the package.
6. `arize-phoenix-evals` contains no trace-completion terms (`IN_PROGRESS`, `end_time`, `inactivity`, `completion buffer`, `lookback`).

## Not tested

What MLflow's store holds for a partial trace, MLflow's real poll interval, real trace durations, MLflow session scoring, the server-side behaviour of Datadog, Arize AX and Confident AI (the Datadog and Arize rules in the article are cited from their documentation, not measured), score accuracy, cost, and latency.
