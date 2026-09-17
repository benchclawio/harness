# LangGraph interrupt() re-execution — does resumed code run once or twice?

**Question:** when a LangGraph run pauses on `interrupt()` and is resumed, does the
interrupted node continue after the `interrupt()` call, or restart from its first line?

**Answer, executed against `langgraph==1.2.11` on 2026-08-17:** it restarts from the first
line. Any side effect placed above `interrupt()` — a charge, an email, a database write —
runs once per resume, not once per run.

## Reproduce

```
pip install langgraph==1.2.11
python 05_interrupt_reexecution.py
```

## Real output (2026-08-17)

See `raw-output-2026-08-17.txt`. `langgraph==1.2.11` was still the current stable release on
PyPI as of 2026-09-17, so this behavior has not been superseded by a later release since the
original run.

## Context

First published as part of
[BenchClaw's LangGraph tutorial](https://benchclaw.io/langgraph-tutorial/), 2026-08-18 —
every snippet in that piece was executed the day before, pinned to `langgraph==1.2.11`. This
script isolates the one finding that surprised us most.
