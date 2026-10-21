# Cursor pricing: public-record read, 2026-10-21

Evidence for https://benchclaw.io/cursor-pricing/. A static read of Cursor's published pricing page and documentation, and Anthropic's
published API rates. No account was used, no model was called, nothing was billed. BenchClaw ran no Cursor session and makes no claim about
how much usage any plan allows.

## What it reads

- https://cursor.com/pricing: the current plans, usage multipliers and billing notes.
- https://cursor.com/docs/models-and-pricing.md: the plan table, annual prices, third-party model rates, top-ups and the Cursor Token Rate.
- https://cursor.com/docs/account/pricing/legacy-cursor-plans.md: the plans Cursor sold before The X Subscription and the plan each maps to.
- https://cursor.com/help/the-x-subscription/overview.md.
- https://platform.claude.com/docs/en/about-claude/pricing.md: Anthropic's own rates. Every Claude row in Cursor's third-party table is
  compared with the Anthropic rate for the same model (15 rows compared, 2 variants with their own multipliers not compared).
- https://code.claude.com/docs/en/costs.md: token counts of one documented agent session, reused for arithmetic.
- Seven pages that rank for "cursor pricing" or are cited by Google's AI Overview, fetched only to see what they mention
  (one returned HTTP 403 and is recorded as such).
- Google's AI Overview for "cursor pricing" (saved text), to check its claims against the live pages.

## Our arithmetic

Only on published prices: annual against monthly billing, the legacy-to-current price changes, price per Plus-sized weekly pool (relative,
since Cursor does not state the pool in dollars), and the documented agent session priced at Cursor's listed Claude Sonnet 5.5 and Opus 5.5
rates with and without the Cursor Token Rate. The token-rate sentence says it applies to "input tokens, output tokens, and cached tokens";
the script computes it both counting all four token types and leaving out cache writes. None of it measures how much usage a plan allows.

## Reproduce

```bash
python3 check_cursor_pricing.py --as-of 2026-10-21 > out.json
```

Two runs on 2026-10-21 produced byte-identical output (sha256 `557ff3aa...c2351a`, see `run_twice.sh`). The pages are read live, so a later run
can differ if the vendors change them; `--as-of` is a label, not a filter.

## Files

- `check_cursor_pricing.py`, `cursor-pricing-2026-10-21.json`, `google-ai-overview-cursor-pricing-2026-10-21.md`
- `reader_commands.sh` (the four commands in the article's "check it yourself" section), `run_twice.sh`, `commit_and_push.sh`

## Limits

We did not read the usage dashboards, the help-centre articles on limits, or the Teams and Enterprise pages beyond the documentation text above.
Whether "cached tokens" in the Cursor Token Rate sentence includes cache writes is not stated, hence the two figures. We did not run Cursor.
