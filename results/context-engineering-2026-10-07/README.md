# Context engineering: what an agent carries before it does any work (2026-10-07)

Evidence for the BenchClaw article on `context engineering`. Two measurements, both read from Anthropic API `usage` objects rather than estimated with a tokenizer.

## 1. Controlled: Claude Code's fixed context (`measure_fixed_context.py`)

Claude Code `2.1.289`, model `claude-haiku-4-5-20251001`, prompt "Reply with the single word OK.", run from an empty temporary directory with user settings excluded (`--setting-sources project`), skills disabled (`--disable-slash-commands`) and only the listed MCP server loaded (`--strict-mcp-config`). Four configurations, three runs each, 12 calls, one attempt per run, no retries.

| Config | Total input tokens (3 runs) | Mean | Added over A |
|---|---|---|---|
| A: empty project | 15,826 / 15,824 / 15,823 | 15,824.3 | - |
| B: A + generated CLAUDE.md, 2,012 words | 18,806 / 18,807 / 18,807 | 18,806.7 | 2,982.4 (1.48 tokens per word) |
| C: A + MCP server, 10 tools | 15,938 / 15,934 / 15,936 | 15,936.0 | 111.7 (11.2 per tool) |
| D: A + MCP server, 40 tools | 16,266 / 16,264 / 16,268 | 16,266.0 | 441.7 (11.0 per tool) |

Total input tokens = `input_tokens + cache_creation_input_tokens + cache_read_input_tokens` of the final API message in the stream. The cache split changes between runs (the first run writes the cache, later runs read it); the total does not. Raw output: `raw-A.json` (A was run first as a check) and `raw-BCD.json`. `summarise.py` builds `summary-2026-10-07.json` and gives identical output on two runs.

The full JSON definitions of the 10 and 40 fixture tools are 4,481 and 17,921 bytes. Adding them cost 112 and 442 tokens, so the definitions were not sent inline. The `init` event lists all the fixture tools by name, and `ToolSearch` is in the base tool list. We did not inspect the request body, so the mechanism is inferred, not observed.

## 2. Observational: first calls in our own logs (`first_turn_context_from_logs.py`)

Run against 103 Claude Code session transcripts on one host (versions 2.1.261, 2.1.283, 2.1.289; Sonnet 5, Sonnet 5.5, Opus 5, Opus 5.5). Output has counts and percentiles only: minimum 6,651, quartiles 42,341 and 83,914, median 64,575, maximum 433,855 tokens; 4 sessions under 20k, 16 over 100k. `first-turn-from-logs-2026-10-07.json`; two runs byte-identical. These sessions include hooks output, memory files, plugins and a first message of any length, and the models differ from measurement 1, so the two are not comparable one-to-one. The transcript count grows as sessions are added, so a later run gives a larger `sessions` value.

## Not measured

Haiku 4.5 only. Claude Code's tool-loading behaviour may differ by model, version and tool count; we did not test Sonnet or Opus, more than 40 tools, or what a deferred tool costs once the model asks for its definition. We did not measure answer quality, latency or dollar cost. The generated CLAUDE.md is plain English; real files with code or tables tokenise differently.

## Google AI Overview

`google-ai-overview-context-engineering-2026-10-07.md`.

## Reproduce

```bash
python3 measure_fixed_context.py --runs 3 --out my-run.json   # needs `claude` logged in; makes 12 calls
python3 first_turn_context_from_logs.py                         # reads ~/.claude/projects, prints counts only
```
