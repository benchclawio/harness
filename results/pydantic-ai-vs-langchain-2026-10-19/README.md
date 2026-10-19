# Pydantic AI and LangChain: public-record read, 2026-10-19

Evidence for https://benchclaw.io/pydantic-ai-vs-langchain/. A static read of public registry, GitHub and wheel records. No package was
installed or run (the published wheels were opened as zip files and never imported), no account was used, no model was called, nothing
was billed. BenchClaw makes no claim about how well either framework works.

## What it reads

- PyPI JSON API for both families (`pydantic-ai`, `pydantic-ai-slim`, `pydantic-graph`; `langchain`, `langchain-core`, `langgraph`,
  `langchain-classic`) plus the other first-party packages a default install pulls in: latest stable version, upload date, stable
  releases in the 90 days before the cut-off, declared base dependencies and declared extras.
- The published wheel of each first-party package, opened as a zip: Python file count, Python source lines, wheel bytes, top-level
  packages, and whether named modules exist (`langchain/chains/`, `langchain_classic/chains/`, `langchain_core/runnables/`,
  `pydantic_ai/ext/langchain.py`). Third-party dependencies (`pydantic`, `httpx`, OpenTelemetry and so on) are not counted.
- pypistats.org downloads for the last month.
- GitHub for `pydantic/pydantic-ai`, `langchain-ai/langchain` and `langchain-ai/langgraph`: licence, archived flag, last commit before
  the cut-off, published security advisories, README sentences about maintenance status.
- Google's AI Overview for "pydantic ai vs langchain" (saved text), to check its checkable claims.

Lines include comments and docstrings, and wheel bytes include data files and type stubs, so the size figures are a rough scale and not a
quality measure. Downloads include automated installs and installs pulled in by other packages. An advisory count measures disclosure,
not safety.

## Reproduce

```bash
export GITHUB_TOKEN=...   # optional; about 20 GitHub requests, the anonymous limit is 60 an hour
python3 check_pydantic_ai_vs_langchain.py --as-of 2026-10-19T18:30:00Z > out.json
```

Two runs on 2026-10-19 produced byte-identical output (sha256 `1a72f75d...f90684`). Versions, uploads, commits and advisories are fixed
by `--as-of`; download counts are the trailing month at read time and move daily. A package that publishes a new stable release after the
cut-off is not counted, but the wheel contents are read from the version that was latest at the cut-off.

## Files

- `check_pydantic_ai_vs_langchain.py`, `pydantic-ai-vs-langchain-2026-10-19.json`, `google-ai-overview-pydantic-ai-vs-langchain-2026-10-19.md`
- `reader_commands.sh` (the four commands in the article's "check it yourself" section, with versions pinned)
- `run_twice.sh`, `commit_and_push.sh` - local helpers (the token comes from the local `gh` credential store and is never printed or written)

## Limits

We did not execute any package, including the `pydantic_ai.ext.langchain` adapter, which we only read. We counted no integration
packages, so the "600+ integrations" claim in Google's AI Overview is unverified. We did not read the `langsmith` client's repository or
either company's ownership. We read no benchmark results for this page.
