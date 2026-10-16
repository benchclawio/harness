# Langfuse and eight alternatives: public-record read, 2026-10-16

Evidence for https://benchclaw.io/langfuse-alternatives/. A static read of public pages and GitHub and PyPI records. No
tool was installed or run, no account was used, no model was called, nothing was billed. BenchClaw makes no claim about
tracing quality, evaluation quality or speed for any of these tools.

## What it reads

- Three announcements: Langfuse joining ClickHouse (ClickHouse and Langfuse posts), Helicone joining Mintlify, Traceloop joining ServiceNow
- The licence file at the root of the Langfuse, Phoenix, Opik and MLflow repositories
- Comet's Opik pricing page (free tier), to check a claim in Google's AI Overview
- GitHub API for nine repositories (Langfuse, Phoenix, Opik, MLflow, Helicone, Laminar, OpenLLMetry, OpenLIT, W&B Weave): licence,
  archived flag, last commit before the cut-off, latest stable release, stable releases in 90 days, published security
  advisories (a count measures disclosure, not safety) and README sentences about deprecation, maintenance mode or moves
- PyPI JSON API for the Python packages: latest stable version, upload date, versions in 90 days
- Google's AI Overview for "langfuse alternatives" (saved text), to check four of its claims

A GitHub release series and a PyPI package are not always the same product. For Langfuse, the GitHub releases are the
platform (v4.x) and the PyPI package `langfuse` is the Python SDK (5.x). The article keeps the two apart.

## Reproduce

```bash
export GITHUB_TOKEN=...   # optional; about 60 GitHub requests, the anonymous limit is 60 an hour
python3 check_langfuse_alternatives.py --as-of 2026-10-16T18:30:00Z > out.json
```

Two runs on 2026-10-16 produced byte-identical output (sha256 `477b3fe3...d65020`). Release and commit dates are fixed by
`--as-of`; announcements, licence files, pricing pages and READMEs are read live.

## Files

- `check_langfuse_alternatives.py`, `langfuse-alternatives-2026-10-16.json`, `google-ai-overview-langfuse-alternatives-2026-10-16.md`
- `reader_commands.sh` - the three commands printed in the article's "check it yourself" section
- `run_twice.sh`, `commit_and_push.sh` - local helpers (the GitHub token comes from the local `gh` credential store and is never printed or written)

## Limits

We read nothing about MLflow's governance, Laminar's or OpenLIT's owners, or any hosted platform's terms. GitHub reports
no single licence for Langfuse or Phoenix; we read their licence files at the repository root. A pricing page read once is
not a price guarantee.
