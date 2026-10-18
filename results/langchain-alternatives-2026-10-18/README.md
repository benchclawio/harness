# LangChain and thirteen alternatives: public-record read, 2026-10-18

Evidence for https://benchclaw.io/langchain-alternatives/. A static read of public registry, GitHub and README records. No
package was installed or run, no account was used, no model was called, nothing was billed. BenchClaw makes no claim about how well
any of these frameworks works.

## What it reads

- PyPI JSON API for the LangChain family (`langchain`, `langchain-core`, `langgraph`, `langchain-classic`, `langchain-community`): version,
  upload date and declared base dependencies. This shows what "leaving LangChain" does and does not remove.
- Per project, thirteen alternatives plus LangChain itself: PyPI (or the npm registry for the two TypeScript projects) for latest stable
  version, upload date and stable releases in the 90 days before the cut-off; pypistats.org or the npm downloads API for the last month;
  GitHub for licence, archived flag, last commit before the cut-off, published security advisories and README sentences about
  maintenance status.
- Google's AI Overview for "langchain alternatives" (saved text), to check three of its claims.
- `licence-files-2026-10-18.txt`: the first lines of the licence files for Vercel AI SDK, Mastra and AutoGen, because GitHub's licence
  field is empty or odd for them (read by `licence_probe.sh`).

Downloads include automated installs and installs pulled in as dependencies of other packages, so they show reach, not the number of
people who chose a framework. An advisory count measures disclosure, not safety.

## Reproduce

```bash
export GITHUB_TOKEN=...   # optional; about 60 GitHub requests, the anonymous limit is 60 an hour
python3 check_langchain_alternatives.py --as-of 2026-10-18T18:30:00Z > out.json
```

Two runs on 2026-10-18 produced byte-identical output (sha256 `efa93f62...9de61a`). Versions, uploads, commits and advisories are fixed by
`--as-of`; download counts are the trailing month at read time and move daily.

## Files

- `check_langchain_alternatives.py`, `langchain-alternatives-2026-10-18.json`, `google-ai-overview-langchain-alternatives-2026-10-18.md`
- `licence_probe.sh`, `licence-files-2026-10-18.txt`, `reader_commands.sh` (the three commands in the article's "check it yourself" section)
- `run_twice.sh`, `commit_and_push.sh` - local helpers (the token comes from the local `gh` credential store and is never printed or written)

## Limits

We did not check whether the LangSmith client sends data when LangChain is used, only that `langchain-core` declares it as a dependency.
We read no benchmark results for this page. GitHub reports no single licence for Vercel AI SDK, Mastra or AutoGen; the licence-file text
is the source for those three.
