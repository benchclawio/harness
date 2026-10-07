# OpenRouter alternatives (bc-110)

Evidence for the BenchClaw article [OpenRouter Alternatives After the Stripe Deal: Fees, Licences and What We Verified](https://benchclaw.io/openrouter-alternatives/).

## What this checks

1. OpenRouter's published fee model (platform fees by plan, bring-your-own-key limits, credit purchase fee, free-plan
   limit) and its own announcement that it is joining Stripe, plus Stripe's newsroom post about the acquisition.
2. The published fee models of Cloudflare AI Gateway, Vercel AI Gateway, Portkey, Helicone and Requesty.
3. GitHub status of four open-source gateways: LiteLLM, Portkey gateway, Helicone and TensorZero (licence, archived flag,
   last push, latest release, releases in the last 90 days).
4. Fee arithmetic for three monthly spend levels.

## Method

- `check_gateway_alternatives.py`: standard library only, no API key, no account, nothing is billed and no gateway is
  called. Run twice on 2026-10-07; the two outputs were byte-identical. It makes eight GitHub API requests; an optional
  `GITHUB_TOKEN` lifts GitHub's unauthenticated limit and was set for these runs.
- `openrouter-alternatives-2026-10-07.json`: the raw, unedited output.
- `google-ai-overview-openrouter-alternatives-2026-10-07.md`: Google's AI Overview text for the query.

## Limits

This is published pricing and repository metadata, not a measurement of routing quality, latency or reliability. The fee
arithmetic assumes all spend is bought as the gateway's own credits, ignores payment processing fees and minimum
charges, and does not cover Portkey or Helicone, which price by logs or requests. Pricing pages are parsed with patterns
tuned to the wording on 2026-10-07. Whether the Stripe acquisition has closed is not stated on either page we read.

## Result (2026-10-07)

- OpenRouter's Standard plan charges a 5.5% platform fee, Business 8%; with your own provider keys the first $25,000 a
  month of list-price inference has no fee and later usage costs 5%.
- OpenRouter announced on 2026-08-19 that it is joining Stripe ("We expect to close in the coming weeks"); Stripe's
  newsroom post "Stripe agrees to acquire OpenRouter" is dated the same day.
- Vercel AI Gateway says no markup and no platform fee on tokens; Cloudflare's example is a $100 credit purchase costing
  $105; Requesty adds 5%.
- TensorZero's GitHub repository is archived (last release 2026-06-04).
