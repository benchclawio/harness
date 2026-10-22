# Claude Duet: public-record read, 2026-10-22

Evidence for https://benchclaw.io/claude-duet/. A static read of Anthropic's and OpenAI's published pages. No account was used, no waitlist
signup was made, no model was called, nothing was billed, and Claude Duet itself was never run. BenchClaw has no access to Claude Duet and
makes no claim about how well it works.

## What it reads

- Anthropic's announcement, https://claude.com/resources/articles/claude-duet (dated 2026-10-21).
- Anthropic's help article "Get started with Claude Duet" (limitations, pricing and usage limits, privacy and safety). It is marked "updated today".
- Anthropic's pricing page, only for the Pro and Max prices (`data-plan` attributes) and to see whether it mentions Duet.
- OpenAI's "Meet dots" documentation (https://learn.chatgpt.com/docs/dots), for the comparison table in the article.
- MacRumors, Engadget and Unite.AI, only to record where their wording differs from Anthropic's own pages.

`check_claude_duet.py` holds 62 sentences copied from those pages (28 from the announcement, 25 from the help article, 9 from OpenAI's docs)
and records whether each one is on the page today. It is a check of what the pages say, not of what the product does.

## Reproduce

```bash
python3 check_claude_duet.py --as-of 2026-10-22 > out.json
```

Two runs on 2026-10-22 produced byte-identical output (sha256 `39f25a1b...51c29a`, see `run_twice.sh`). The pages are read live, and Anthropic's help
article says it was updated today, so a later run can differ; `--as-of` is a label, not a filter.

## Files

- `check_claude_duet.py`, `claude-duet-2026-10-22.json`
- `reader_commands.sh` (the four commands in the article's "check it yourself" section), `run_twice.sh`, `commit_and_push.sh`

## Limits

We did not run Claude Duet, join the waitlist or read Meta's pages. Anthropic's safety claims (credential handling, the sensitive-information classifier,
the external penetration test) and OpenAI's access rules are the vendors' statements. No independent test of either product was found.
