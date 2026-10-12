# AI agent memory libraries: public-record read, 2026-10-12

Evidence for https://benchclaw.io/ai-agent-memory/. A static read of public records for seven agent-memory
projects. No memory library was installed, imported or run, and nothing here measures how well any of them
remembers. Standard library only; no account; nothing billed.

## What it reads

- GitHub API: licence, language, archived flag, last commit before the cut-off, latest stable release,
  stable releases in the 90 days before the cut-off, published security advisories, README status sentences
- PyPI JSON API: latest stable version before the cut-off, upload date, versions in 90 days, declared
  dependencies (with and without extras), required Python, summary line and `Source` link
- pypistats.org recent-downloads endpoint: downloads in the last month (automated installs included)
- Four claims in Google's AI Overview for "ai agent memory", saved in
  `google-ai-overview-ai-agent-memory-2026-10-12.md`

Projects: Mem0, Graphiti, Zep (repository), Letta (old repository), Letta Code, LangMem, Cognee, Supermemory.

## Reproduce

```bash
export GITHUB_TOKEN=...   # optional; the script makes about 45 GitHub requests, the anonymous limit is 60 an hour
python3 check_agent_memory.py --as-of 2026-10-12T19:00:00Z > out.json
```

Two runs on 2026-10-12 produced byte-identical output (sha256 `a3ac32ff...3c019`, file
`agent-memory-2026-10-12.json`). Download counts and "latest" values move with time; the `--as-of` cut-off fixes
releases, commits and advisories, but not pypistats, which always reports the trailing month at read time.

## Files

- `check_agent_memory.py` - the checker
- `agent-memory-2026-10-12.json` - its output
- `google-ai-overview-ai-agent-memory-2026-10-12.md` - the AI Overview text, one DataForSEO call
- `reader_commands.sh` - the three commands shown in the article's "check it yourself" section
- `run_with_token.sh`, `run_twice.sh`, `probe_advisories.sh` - local helpers (the token is read from the local `gh`
  credential store and is never printed or written)

## Limits

An empty advisory list means none are published on GitHub, not that none exist. Supermemory's npm record was
not read. Zep Cloud, Mem0 Platform and Letta Cloud terms were not read.
