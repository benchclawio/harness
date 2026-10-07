# Claude Code vs Codex (bc-109)

Evidence for the BenchClaw article [Claude Code vs Codex: Pricing, Licences and What We Could Verify](https://benchclaw.io/claude-code-vs-codex/).

## What this checks

Published facts about the two coding CLIs, read on 2026-10-07: npm release cadence and licence fields for
`@anthropic-ai/claude-code` and `@openai/codex`, GitHub repository metadata, the first line of each
repository's licence file, and the two vendors' public pricing pages parsed into numbers (Claude Pro and Max;
ChatGPT Free, Go, Plus and Pro with Codex, the published local-message ranges per model, and the stated
retirement of GPT-5.5).

## Method

- `check_claude_code_vs_codex.py`: standard library only, no API key, no account, nothing is billed and
  neither tool is run. Run twice on 2026-10-07; the two outputs were byte-identical. It makes two GitHub API
  requests; an optional `GITHUB_TOKEN` environment variable lifts GitHub's unauthenticated limit (not needed here).
- `claude-code-vs-codex-2026-10-07.json`: the raw, unedited output.
- `google-ai-overview-claude-code-vs-codex-2026-10-07.md`: Google's AI Overview text for the query, because the
  article checks its claims.

## Limits

This is published metadata and pricing, not a measurement. We ran neither tool as a benchmark, so nothing here
says which is faster or writes better code. Pricing pages are parsed with patterns tuned to the wording on
2026-10-07 and will drift. Usage limits are the vendors' own estimates. npm release counts show how often each
package ships, not whether releases are good; Claude Code and Codex also ship through installers.

## Result (2026-10-07)

- Claude Pro is $20 a month ($17 with annual billing) and includes Claude Code; Max starts at $100 and is sold as
  5x or 20x more usage than Pro, with no absolute usage numbers.
- ChatGPT Plus is $20 a month and includes Codex in the CLI, IDE and web; Pro starts at $100 ($100, $200 or $500);
  Plus local-message ranges per five hours are published for four models (for example GPT-6.1 Sol 15-160).
- Codex CLI is Apache-2.0 (Rust). Claude Code's repository licence file reads "All rights reserved" and points to
  Anthropic's Commercial Terms of Service.
