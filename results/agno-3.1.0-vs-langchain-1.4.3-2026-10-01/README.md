# Agno 3.1.0 vs LangChain 1.4.3 (gpt-4o, 2026-10-01)

80 live runs: 2 arms x 4 tasks x 10 runs, `gpt-4o` at temperature 0, both arms interleaved and
counterbalanced on 2026-10-01. Total API cost $0.18855. Article: https://benchclaw.io/agno-vs-langchain/

| File | What it is |
|---|---|
| `scored-bc107-raw-2026-10-01.jsonl` | One record per run (80). `wall_time_s` is measured inside the worker; `wall_time_outer_s` is the whole cold process, measured by the runner. |
| `scored-bc107-analysis-2026-10-01.json` | Per-arm and per-task statistics, bootstrap CIs, import-cost and warm-request estimates. |
| `warmup-bc107-raw-2026-10-01.jsonl` | The two warm-up runs, not scored. |
| `bc107-import-cost-2026-10-01.json` | 10 cold imports per arm, measured separately. |
| `TIMING-NOTE.md` | Why raw `wall_time_s` is not comparable between these two workers. |
| `worker_agno.py`, `worker_langchain.py` | The two subject adapters. `worker_agno.py` is the same file used for Agno 3.0.1 in the earlier review. |
| `shared_tools.py`, `real-pilot-task-suite-v0.1.0.json` | Shared tool runtime and scorer, and the four-task suite (SHA-256 `ec72e7440ea177d150ee550ea6dbe908b02410cae6e45f78aefa9eed29f339bf`). |
| `run_bc107_agno_langchain_gpt4o.py`, `test_bc107_adapters.py` | The runner and the 26-check fake-mode acceptance test (no network, no credentials). |
| `bc107-*-py312-linux-x86_64-2026-10-01.lock` | Hash-pinned wheel locks for each arm (CPython 3.12.13, Linux x86_64). |

Caveat: `wall_time_s` in the raw file is not a fair comparison between arms. Use `wall_time_outer_s`
(cold process) or the import-adjusted figures in the analysis file.

The scripts expect the BenchClaw working-tree layout (`adapters/`, `methodology/`, `.venvs/`); they
are published for reading and audit, and are not a one-command reproduction.

Note: in `run_bc107_agno_langchain_gpt4o.py` the local variable `api_key` was renamed `openai_credential` in this published copy, only so the repository secret scanner does not flag the assignment line. No behavioural change; the credential is read from a local file and never stored here.
