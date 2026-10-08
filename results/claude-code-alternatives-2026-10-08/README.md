# Claude Code alternatives: licence, release and provider-page check (2026-10-08)

Evidence for the BenchClaw article on `claude code alternatives`. **No tool was installed, run or benchmarked and no model was called.** The script reads public GitHub and documentation pages only.

`check_coding_agents.py` (Python standard library, no key; optional `GITHUB_TOKEN` lifts GitHub's 60-requests-an-hour limit) reads, for Claude Code and eight alternatives: the licence (GitHub's SPDX id and the first line of the licence file), the archived flag, the latest stable release, the last commit, README lines that mention a free tier or a subscription, and how many times one provider documentation page names Anthropic.

Release and commit dates use a fixed cut-off, `--as-of 2026-10-08T18:00:00Z`, so two runs minutes apart agree. Licence, archived flag, README and documentation text are the state when you run it. Output is `coding-agents-2026-10-08.json`; two runs of the final script were byte-identical.

A release counts as stable when GitHub does not flag it a pre-release, its tag has none of nightly, alpha, beta, rc, preview, canary or dev, and its tag matches the main product series (`v1.2.3`; `rust-v0.161.0` for Codex CLI). Cline also tags `cli-`, `desktop-` and `sdk/` releases in the same repository; those are ignored. If five pages of releases hold no stable one, GitHub's latest-release endpoint is used.

## What a mention count means

"Anthropic mentions" is a count of the word on one page. It shows the project documents Anthropic as a provider where the count is large. It is not a test that the connection works, and a zero means only that the page we read does not say it. For Gemini CLI and Crush we read the README only.

## Not measured

Speed, answer quality, price, install or sign-in friction, model support in practice, or whether any tool works with a Claude subscription. GitHub's licence detector returned `NOASSERTION` for Crush and GitHub Copilot CLI and nothing for Claude Code; the article reads those three licence files.

## Google AI Overview

`google-ai-overview-claude-code-alternatives-2026-10-08.md`.

## Reproduce

```bash
python3 check_coding_agents.py > mine.json     # about 2 minutes
```
