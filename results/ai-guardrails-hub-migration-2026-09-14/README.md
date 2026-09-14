# Guardrails Hub → PyPI migration check (bc-080)

Evidence for the BenchClaw article [AI Guardrails: What They Block, and What Just
Changed](https://benchclaw.io/ai-guardrails/).

## What this checks

On 2026-07-06 Guardrails AI announced it was discontinuing `guardrails hub install`, the
private validator registry, and hosted remote inference, with a hard cutoff of 2026-08-25
([migration issue #1560](https://github.com/guardrails-ai/guardrails/issues/1560)). Validators
would instead be plain PyPI packages named `guardrails-ai-<name>`.

This checks, as of the article's publish date, how many of the 65 validators listed on
[guardrails Hub](https://guardrailsai.com/hub) are actually installable that way.

## Method

1. `hub-validator-slugs-2026-09-14.txt` — the 65 validator slugs, extracted from the Hub
   listing page on 2026-09-14.
2. `check_guardrails_pypi_migration.py` — standard-library only, no dependencies, no API key.
   For each slug it queries PyPI's public JSON API (`pypi.org/pypi/<package>/json`) for the
   package `guardrails-ai-<slug-with-dashes>` and records whether it exists, its current
   version, and release date.
3. `guardrails-pypi-migration-2026-09-14.json` — the raw, unedited output.

## Result

64 of 65 found by the mechanical naming rule. The 65th (`restricttotopic` on the Hub) uses an
irregular package name, `guardrails-ai-restrict-to-topic`, confirmed by hand — see
`note_on_missing` in the JSON. All 65 Hub-listed validators are on PyPI.

## Verify locally

```bash
python3 check_guardrails_pypi_migration.py hub-validator-slugs-2026-09-14.txt out.json
```

No API key, no `pip install`, no network dependency beyond PyPI's public JSON API.
