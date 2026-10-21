# Claude Code pricing: public-record read, 2026-10-21

Evidence for https://benchclaw.io/claude-code-pricing/. A static read of Anthropic's published pricing pages and Claude Code cost
documentation. No account was used, no API key, no model was called, nothing was billed. BenchClaw ran no Claude Code session and makes no
claim about how much usage any plan allows.

## What it reads

- https://claude.com/pricing: Pro, Max and Team seat prices (including the `data-plan` price attributes in the page HTML), Enterprise
  terms, API rates for the current models, and the plan FAQ (usage windows, weekly limits, usage credits, Claude Code inclusion).
- https://platform.claude.com/docs/en/about-claude/pricing.md: the full API price table (input, 5-minute and 1-hour cache writes, cache hits,
  output). The pricing page's current-model rates are compared with it.
- https://code.claude.com/docs/en/costs.md: how Claude Code is billed, Anthropic's own spend statement, and one worked session
  (Sonnet 4.6, 1.2k input, 5.3k output, 940.0k cache read and 50.0k cache write tokens, $0.55). The script recomputes that session
  from the documented rates and stops if it does not get $0.55.
- Six pages that rank for "claude code pricing", fetched only to see which prices and model names they mention.
- Google's AI Overview for "claude code pricing" (saved text), to check its claims.

## Our arithmetic

Only on published prices: annual against monthly billing, minimum seat spend, the same documented session priced at the current Sonnet 5.5,
Opus 5.5 and Fable 5.1 rates (5-minute cache write rate, the one the documented session used), and the documented per-developer spend
statement multiplied by 20 active days. None of it measures how much usage a plan allows. Anthropic's FAQ says there is no fixed message count.

## Reproduce

```bash
python3 check_claude_code_pricing.py --as-of 2026-10-21 > out.json
```

Two runs on 2026-10-21 produced byte-identical output (sha256 `7b04840a...6d1b4d`, see `run_twice.sh`). The pages are read live, so a later run can
differ if Anthropic changes them; `--as-of` is a label, not a filter.

## Files

- `check_claude_code_pricing.py`, `claude-code-pricing-2026-10-21.json`, `google-ai-overview-claude-code-pricing-2026-10-21.md`
- `reader_commands.sh` (the four commands in the article's "check it yourself" section), `run_twice.sh`, `commit_and_push.sh`

## Limits

The Max 20x price is not in the pricing page's HTML (the page shows "From $100"), so it is not verified here. We did not read Anthropic's
support articles on usage limits, did not run Claude Code, and did not check the "monthly API credits" terms. Third-party reports of past
limit changes were not verified.
