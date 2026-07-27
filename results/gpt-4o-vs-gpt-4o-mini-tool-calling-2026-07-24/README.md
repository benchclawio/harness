# GPT-4o vs GPT-4o mini tool-calling pilot

This directory contains the sanitized evidence behind BenchClaw's 80-run
GPT-4o vs GPT-4o mini tool-calling pilot, executed on 2026-07-24.

## Test matrix

- Models: `gpt-4o` and `gpt-4o-mini`
- Framework adapters: LangGraph 1.2.9 and Pydantic AI Slim 2.13.0
- Tasks: four deterministic tool-use tasks
- Runs: five per model/framework/task cell; 80 scored runs total
- Temperature: 0
- Parallel tool calls: disabled
- Task suite: v0.1.1
- Task-suite SHA-256:
  `ec72e7440ea177d150ee550ea6dbe908b02410cae6e45f78aefa9eed29f339bf`

## Files

- `scored-pilot-gpt4o-raw-2026-07-24.jsonl` — 40 GPT-4o run records
- `scored-pilot-gpt4o-analysis-2026-07-24.json` — GPT-4o summary
- `scored-pilot-raw-2026-07-24.jsonl` — 40 GPT-4o mini run records
- `scored-pilot-analysis-2026-07-24.json` — GPT-4o mini summary
- `gpt4o-pilot-manifest-v0.4.0.json` — GPT-4o execution manifest
- `real-pilot-status-manifest-v0.3.0.json` — GPT-4o mini execution manifest
- `SHA256SUMS` — checksums for every published evidence file

## Interpretation limits

This is a pilot, not a production model benchmark. The 40 runs per model are
distributed across four tasks and two framework adapters. The GPT-4o mini run
was interrupted by host memory pressure and completed later with the same
workers, inputs, scorer, and model settings. No completed result was rerun or
discarded.

The public manifest copies replace the local credential-file location with
`redacted_local_secret_store`. No credential value was present in the source
artifacts.
