# Prompt caching: public-record read, 2026-10-21

Evidence for https://benchclaw.io/prompt-caching/. A static read of Anthropic's, OpenAI's and Google's published pricing and caching pages and
Amazon Bedrock's caching guide. No API key, no account, no model was called, nothing was billed. BenchClaw sent no request and measured no
hit rate or latency, so every saving in the article is arithmetic on published prices and an upper bound.

## What it reads

- Anthropic: the API price table (input, 5-minute and 1-hour cache write, cache hit and output for every model) and the prompt-caching guide.
- OpenAI: the pricing page (standard tables: input, cached input, and the 30-minute and 12-hour write prices) and the prompt-caching guide,
  including its "summary of model differences" table.
- Google: the Gemini pricing page (the Standard table of each model's context-caching price, with any dated price change and storage price)
  and the context-caching guide (minimum token counts, implicit and explicit caching).
- Amazon Bedrock's prompt-caching guide (checkpoints, minimum token counts).
- Google's AI Overview for "prompt caching" (saved text), to check its claims.

## Our arithmetic

Only on published prices: the input side of one 50,000-token prefix, used once to write the cache and then repeated N times, with every
repeat hitting the cache. It leaves out output tokens, misses, expiry and the cost of anything that is not that prefix. It is an upper bound on savings.

## Reproduce

```bash
python3 check_prompt_caching.py --as-of 2026-10-21 > out.json
```

Two runs on 2026-10-21 produced byte-identical output (sha256 `d857c275...cfd871`, see `run_twice.sh`). The pages are read live, so a later run can
differ if the vendors change them; `--as-of` is a label, not a filter.

## Files

- `check_prompt_caching.py`, `prompt-caching-2026-10-21.json`, `google-ai-overview-prompt-caching-2026-10-21.md`
- `reader_commands.sh` (the four commands in the article's "check it yourself" section), `run_twice.sh`, `commit_and_push.sh`

## Limits

No request was sent, so hit rates, latency and quality are not measured. Amazon Bedrock's and Azure OpenAI's prices were not read. Anthropic's price
table rows for retired models are read but not used in the article.
