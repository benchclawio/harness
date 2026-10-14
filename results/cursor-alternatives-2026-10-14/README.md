# Cursor and nine alternatives: public-record read, 2026-10-14

Evidence for https://benchclaw.io/cursor-alternatives/. A static read of public pages and GitHub records. No tool
was installed or run, no account was used, no model was called, nothing was billed. BenchClaw makes no claim about
how well any of these editors or agents works.

## What it reads

- Cursor's own blog post about its acquisition, its blog index and its pricing page
- Windsurf's pricing page (windsurf.com now serves the "Devin Desktop" site), Zed's pricing page, roocode.com's homepage
- GitHub API for eight repositories (Cline, Kilo Code, Zed, VS Code, VS Code Copilot Chat, Continue, Roo Code, Void):
  licence, archived flag, last commit before the cut-off, latest stable release, stable releases in 90 days, latest
  release of any kind, published security advisories, and README sentences saying whether the project is maintained,
  deprecated, read-only or moved. An advisory count measures disclosure, not safety.
- The licence files at the root of the Zed repository
- Google's AI Overview for "cursor alternatives" (saved text), to check its licence and price claims

Cursor, Windsurf and Zed are not scored on GitHub activity: Cursor and Windsurf are closed products, and we read
their pages only.

## Reproduce

```bash
export GITHUB_TOKEN=...   # optional; about 40 GitHub requests, the anonymous limit is 60 an hour
python3 check_cursor_alternatives.py --as-of 2026-10-14T17:30:00Z > out.json
```

Two runs on 2026-10-14 produced byte-identical output (sha256 `42c45620...c2bf24`). Release and commit dates are
fixed by `--as-of`; pages, READMEs and licence files are read live.

## Files

- `check_cursor_alternatives.py`, `cursor-alternatives-2026-10-14.json`, `google-ai-overview-cursor-alternatives-2026-10-14.md`
- `reader_commands.sh` - the three commands printed in the article's "check it yourself" section
- `run_with_token.sh`, `run_twice.sh`, `commit_and_push.sh` - local helpers (the token comes from the local `gh`
  credential store and is never printed or written)

## Limits

Zed's GitHub licence is reported as NOASSERTION; we read the licence files at the repository root and nothing else.
We found no shutdown announcement for Roo Code; we report the archived flag, the last commit and what roocode.com now
leads with. A pricing page read once is not a price guarantee.
