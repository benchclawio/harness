# Pinecone pricing (bc-113)

Evidence for the BenchClaw article [Pinecone Pricing: What It Costs and When It Adds Up](https://benchclaw.io/pinecone-pricing/).

**No Pinecone account was opened, no index was created and nothing was billed.** The script reads public pages only.

## What this checks

Pinecone's published pricing as read on 2026-10-09: plan prices and limits, the per-unit rates, the billing formulas in its cost documentation, and the dated pricing changes in its 2026 changelog. It also compares what Google's AI Overview and one third-party explainer (withorb.com) say against the live pricing page.

## Method

- `check_pinecone_pricing.py`: Python standard library only, no key. Reads `pinecone.io/pricing`, the cost documentation and 2026 changelog (published as Markdown by appending `.md`), the withorb.com explainer, and `google-ai-overview-pinecone-pricing-2026-10-09.md` from this directory. Prints one JSON document.
- Before it computes anything of ours, it recomputes the worked examples Pinecone publishes in the cost documentation: 4 dense and 4 sparse storage sizes, 5 query read-unit rows, 3 fetch rows, 5 upsert and 5 delete write-unit rows. It exits non-zero if any of those differ. Two further tables are reported as data instead: hybrid storage (2 of 4 rows differ) and update write units (1 of 5 rows differs).
- `pinecone-pricing-2026-10-09.json`: the raw, unedited output. Two runs on 2026-10-09 were byte-identical.
- `google-ai-overview-pinecone-pricing-2026-10-09.md`: Google's AI Overview text for the query, from one live SERP call, because it quotes Pinecone numbers.

## How the arithmetic works

Rates are from the pricing page; where the page gives a range ("varies by cloud and region") we compute both ends. Sizes use the documented formula `records x (ID + metadata + dimensions x 4 bytes)` with 8-byte IDs and 1 GB = 10^9 bytes. A query costs 1 read unit per GB of the namespace it targets, minimum 0.25. An upsert costs 1 write unit per KB of request, minimum 5 per request, so we batch 100 records.

## Limits

We read the published pages. We have not seen an invoice, so every workload is arithmetic from published rates, not an observed bill. Egress is not modelled (it depends on response size); the plan allowances are quoted instead. Dedicated Read Nodes are billed at hourly rates the pricing page does not list, so they are out of scope. Pricing pages change; check the live page before budgeting.

## Reproduce

```bash
python3 check_pinecone_pricing.py > mine.json     # about 20 seconds
```
