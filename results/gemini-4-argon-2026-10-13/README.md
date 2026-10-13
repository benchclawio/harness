# Gemini 4 Argon: public-page read, 2026-10-13

Evidence for https://benchclaw.io/gemini-4-argon/. A static read of Google's public pages and one independent
index page. No Gemini API call was made, no account was used, nothing was billed, and **BenchClaw ran no model
and measured nothing about Argon's quality**. Every benchmark number is Google's own, as printed in its model card.

## What it reads

- DeepMind model card (benchmark table, distribution channels, knowledge cutoff, Frontier Safety Framework notes)
- Google blog: 2026-09-30 announcement and 2026-10-13 availability post
- Gemini API pricing and models pages (endpoint, per-tier prices, price step-up date)
- Artificial Analysis model page (independent index score and rank)

From the model card's table it counts on how many benchmarks Argon is highest among the four models Google chose
to show (Gemini 4 Argon, GPT-6 Astra, Claude Fable 5.1, Claude Opus 5.5), and lists where it is not.

## Reproduce

```bash
python3 check_argon.py > out.json
```

Pages change. The JSON records what each page said when read on 2026-10-13 (about 17:50 UTC).

## Files

- `check_argon.py` - the checker; `argon-2026-10-13.json` - its output
- `reader_commands.sh` - the commands printed in the article's "check it yourself" section

## Limits

Vendor-reported benchmarks are not independently reproduced here. The pricing page is the one we read once;
Google can change it. We did not read the Safety & Security Report (the model card said it was coming 2026-10-13).
