# bc-107: timing-window asymmetry found in bc-057 (2026-10-01)

`wall_time_s` is measured inside each worker from `main()`. `worker_agno.py` imports Agno lazily
inside `run_with_live_model`, so Agno's import cost (about 1.0-1.4 s) is inside the window.
`worker_langgraph.py` and `worker_langchain.py` import at module top, outside it.

Effect on the published bc-057 review (Agno 3.0.1, 2026-08-29, 20 runs per arm):

| View | Agno 3.0.1 | LangGraph 1.2.9 | Gap |
|---|---|---|---|
| Inner mean (as published) | 4.45 s | 2.92 s | +52% |
| Inner mean minus Agno import (about 1.4 s) | about 3.05 s | 2.92 s | about +4% |
| Outer mean (whole cold process) | 5.03 s | 4.20 s | +20% |

The published "59% slower" (medians 4.27 vs 2.68 s) is mostly an import-timing artifact. Pydantic AI
imports part of its OpenAI stack lazily too, so its number is partly affected as well.

bc-107 reports outer (cold process) and import-adjusted request time, never raw inner. The bc-057
raw data is unchanged and still valid; only the headline comparison needs correcting.
Decision on editing /agno-review/'s headline belongs to Neo.
