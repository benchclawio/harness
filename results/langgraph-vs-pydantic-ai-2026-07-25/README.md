# LangGraph 1.2.9 vs Pydantic AI 2.13.0

This is the sanitized evidence bundle for BenchClaw study `bc-004-full-2026-07-25`.

- Run date: 2026-07-25
- Model: OpenAI gpt-4o
- Temperature: 0
- Subjects: `langgraph==1.2.9` and `pydantic-ai-slim[openai]==2.13.0`
- Design: four tasks, 20 scored runs per subject per task, 160 total runs
- Result: 160/160 completed
- Total recorded model cost: $0.3767

Files:

- `bc004-full-raw-2026-07-25.jsonl` — 160 sanitized terminal run records
- `bc004-analysis-2026-07-25.json` — aggregate and paired analysis
- `bc004-manifest-2026-07-25.json` — versions, frozen-input digest, artifact digests, and run counts
- `SHA256SUMS` — file integrity checksums

The frozen task suite is [`task-suites/pilot-v0.1.1.json`](../../task-suites/pilot-v0.1.1.json). Its SHA-256 digest matches the task-suite digest recorded for the study.

Read the [full benchmark report](https://benchclaw.io/langgraph-vs-pydantic-ai-benchmark/) and [methodology](https://benchclaw.io/methodology/) for interpretation, caveats, scoring rules, and the statistical plan.
