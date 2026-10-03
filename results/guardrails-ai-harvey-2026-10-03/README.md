# Guardrails AI after the Harvey acquisition (bc-101)

Evidence for the BenchClaw article [Guardrails AI Joins Harvey: What We Verified About the
Open-Source Project](https://benchclaw.io/guardrails-ai-harvey-acquisition/).

## What this checks

Harvey announced its acquisition of Guardrails AI on 2026-09-08/09. The announcement says
nothing about the open-source framework, so this reads what is publicly verifiable on
2026-10-03: the announcement text, the repository licence, commit and release activity,
the README, the 1.0 design issue, PyPI metadata, three public download counters, and two
retired Guardrails endpoints.

## Method

- `check_guardrails_post_acquisition.py`: standard library only, no API key, one run, prints
  one JSON document. Uses unauthenticated GitHub REST (about 8 requests), PyPI, pypistats.org,
  pepy.tech and one DNS lookup.
- `guardrails-ai-harvey-2026-10-03.json`: the raw, unedited output of that run.

No model was called and no guardrail was run. This is source inspection, not a benchmark.

## Result (2026-10-03)

- Licence Apache-2.0 on GitHub and PyPI; repository not archived; `guardrails-ai` 0.11.0.
- 0 commits to the default branch on or after 2026-09-08; the latest is 2026-08-26.
- README mentions of Harvey or the acquisition: 0.
- Last 30 days of downloads: 102,281 to 107,131 by daily sums, 93,421 from pypistats'
  `recent` endpoint. The announcement claims more than 250,000 a month. The highest month in
  pypistats' retained history is April 2026 at 249,659 with mirrors.
- `hub.api.guardrailsai.com` does not resolve; `pypi.guardrailsai.com/simple/` returns 401
  without credentials.

Activity and download figures change daily, so a rerun will differ from the committed JSON.

## Verify locally

```bash
python3 check_guardrails_post_acquisition.py
```
