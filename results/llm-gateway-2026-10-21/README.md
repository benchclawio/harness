# LLM gateways: public-record read, 2026-10-21

Evidence for https://benchclaw.io/llm-gateway/. A static read of public GitHub records, vendor announcements and one incident notice. No gateway was
installed, run or called, no account was used, no model was called, nothing was billed. BenchClaw makes no claim about the speed or reliability of any gateway.

## What it reads

- GitHub for nine open-source gateway repositories (LiteLLM, Bifrost, LLM Gateway at llmgateway.io, agentgateway, Envoy AI Gateway, Kong Gateway, Portkey's gateway,
  Helicone, TensorZero): licence (SPDX and the first lines of the LICENSE file), main language, archived flag, last commit, latest stable release, releases in the
  last 90 days, published security advisories, and how often the README mentions ten feature words. The mention counts show what a README emphasises; they are not
  a test that the feature works, and a zero does not mean the project lacks it.
- Palo Alto Networks' release on the Portkey acquisition, Stripe's announcement about OpenRouter, and LiteLLM's own March 2026 security notice.
- llmgateway.io's home page, for the model and provider counts Google's AI Overview repeats.
- Google's AI Overview for "llm gateway" (saved text), to check its claims.

An advisory count measures disclosure, not safety.

## Reproduce

```bash
export GITHUB_TOKEN=...   # optional; about 70 GitHub requests, the anonymous limit is 60 an hour
python3 check_llm_gateway.py --as-of 2026-10-21T19:00:00Z > out.json
```

Two runs on 2026-10-21 produced byte-identical output (sha256 `7345a76c...65dee5`, see `run_twice.sh`). Versions, releases, commits and advisories are
fixed by `--as-of`; page text is read live, so a later run can differ.

## Files

- `check_llm_gateway.py`, `llm-gateway-2026-10-21.json`, `google-ai-overview-llm-gateway-2026-10-21.md`
- `reader_commands.sh` (the four commands in the article's "check it yourself" section), `run_twice.sh`, `commit_and_push.sh`

## Limits

We did not read any gateway's documentation beyond its repository README and licence file, tested no feature, and did not check whether Stripe's OpenRouter deal
has closed. Hosted gateways (OpenRouter, Cloudflare AI Gateway, Vercel AI Gateway) are closed products and were not read.
