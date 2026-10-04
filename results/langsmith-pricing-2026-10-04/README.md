# LangSmith pricing (bc-102)

Evidence for the BenchClaw article [LangSmith Pricing: What It Costs and When It Adds Up](https://benchclaw.io/langsmith-pricing/).

## What this checks

LangSmith's published pricing, read on 2026-10-04: plan prices, included traces, the per-trace
rate, retention periods and what the docs say about billing. It also records what one
third-party pricing explainer (agentsapis.com) claims for the same numbers, and does the
arithmetic for seven example workloads.

## Method

- `check_langsmith_pricing.py`: standard library only, no API key, no account, nothing is
  billed. Reads langchain.com/pricing (page text, the per-trace tooltip and the calculator
  constants in the page script), two docs pages and the agentsapis.com page. Prints one JSON
  document. Run twice on 2026-10-04; the two outputs were byte-identical.
- `langsmith-pricing-2026-10-04.json`: the raw, unedited output.
- `google-ai-overview-langsmith-pricing-2026-10-04.md`: Google's AI Overview text for the
  query, from one live SERP call, because it quotes a per-trace price.

## Limits

We read the published page. We have not opened a LangSmith account or seen an invoice, so the
example workloads are arithmetic from published rates, not observed bills. The page does not
say whether the extended-retention upgrade fee applies to the included traces; the script
assumes it applies to billable traces only. Pricing pages change, so check the live page
before budgeting.

## Result (2026-10-04)

- Developer $0 (1 seat, 5,000 base traces); Plus $39 per seat per month (10,000 base traces);
  Enterprise custom, with self-hosted and hybrid.
- 1 LSU = $1. Base trace 0.005 LSU = $5.00 per 1,000. Extended-retention upgrade 0.0025 LSU
  = $2.50 per 1,000, so $7.50 per 1,000 for an extended trace.
- Retention: 14 days base, 180 days extended (the docs say the SaaS maximum changed to 180
  days on 2026-09-14).
- agentsapis.com quotes $2.50, $5.00 and $2.50 per 1,000 and a 400-day extended retention.
