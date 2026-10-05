# Langfuse pricing (bc-103)

Evidence for the BenchClaw article [Langfuse Pricing: Cloud Plans, Units and Self-Hosting Cost](https://benchclaw.io/langfuse-pricing/).

## What this checks

Langfuse's published Cloud plans, graduated usage rates, billable-unit definition, the
self-hosted (Open Source vs Enterprise) feature split and the documented minimum
infrastructure for self-hosting, all read on 2026-10-05. It then does the arithmetic for a
grid of example workloads and a comparison with LangSmith Plus at the same trace volumes.

## Method

- `check_langfuse_pricing.py`: standard library only, no API key, no account, nothing is
  billed. Reads four langfuse.com pages as Markdown (append `.md`) and LangSmith's pricing
  page for the comparison rates. **Before computing anything it reproduces the five worked
  examples Langfuse publishes on its own pricing page (200k, 1M, 5M, 25M and 100M units); if
  any differ it exits non-zero.** All five matched. Run twice on 2026-10-05; the two outputs
  were byte-identical.
- `langfuse-pricing-2026-10-05.json`: the raw, unedited output.
- `hetzner-cx53-price-2026-10-05.json`: the list price of one Hetzner Cloud server type, read
  from the Hetzner Cloud API (read-only, no server was created). It is a snapshot because the
  API needs a token; the same list price is on Hetzner's public pricing page.

## Limits

We read published pages. We opened no Langfuse account and saw no invoice, so every dollar
figure is arithmetic on published rates. The units-per-trace values (1, 7 and 20) are
assumptions for sensitivity: 7 comes from the single worked example in Langfuse's own
billable-units documentation (140,131 units from 20,070 traces). We did not deploy Langfuse,
so the self-hosting cost is a list-price example for the documented minimum footprint, not a
measured deployment. It excludes object storage, backups, high availability, bandwidth and
operator time.

## Result (2026-10-05)

- Cloud: Hobby $0 (50k units, 2 users, 30 days), Core $29 (100k units, unlimited users, 90
  days), Pro $199 (100k units, 3 years), Enterprise $2,499. Extra units $8 per 100k, falling to
  $6 above 50M. Teams add-on $300 a month.
- A unit is a trace, an observation or a score.
- Documented minimum self-hosting footprint: 9 vCPU and 21.5 GiB across five services.
- At 100,000 traces a month and 7 units per trace, Core costs $77; LangSmith Plus costs $489
  with one seat and $645 with five.
