# AI agent evaluation tools — bc-038 evidence

Status: **v0.1.0 pilot complete but invalid for ranking; v0.2.0 rerun pre-registered**.

The first run completed 840 evaluations with no execution errors. The post-run corpus audit
then found two label/input defects before publication. We retain that run here because
hiding a failed benchmark design would defeat the point of an open evidence bundle.

Do not quote the v0.1.0 arm rates as product rankings. Read
`bc038-pilot-audit-2026-08-14.md` first.

## What is frozen for the rerun

- Corpus: `bc038-corpus-v0.2.0.json`
- Corpus SHA-256: `156e332faa5531d65395c17535eded75cff5dee64c395dec83bf99184bc4e1e2`
- Specification: `../../methodology/bc038-corpus-spec-v0.2.0.md`
- Manifest: `../../methodology/bc038-rerun-manifest-v0.2.0.json`
- Judge: `gpt-4o-2024-08-06`, temperature 0, enforced by the local request ledger
- Arms: naive OpenAI call, Phoenix Evals 3.4.0, DeepEval 4.1.8, Opik 2.2.28
- 70 cases × 3 repeats × 4 arms = 840 measured evaluations

The v0.2.0 corpus repairs the two pilot defects:

1. `format_violation` now includes the restock policy in the visible tool trajectory.
2. `wrong_tool_sequence` offers the required price tool and varies only whether it was
   called; the final answer is identical across the matched pair.

The request ledger records model, temperature, usage and response provenance without
storing prompts, outputs, headers or credentials. Its offline tests are in
`test_bc038_v0_2.py`.

## Pilot files

- `bc038-corpus-v0.1.0.json` — preserved pilot corpus
- `bc038-eval-*.jsonl` — four raw pilot arms, 210 rows each
- `eval.log` — gates and execution log
- `bc038-analysis-2026-08-14.json` — reproducible pilot analysis
- `bc038-pilot-audit-2026-08-14.md` — why the pilot is invalid for ranking

## Reproduce local checks

```bash
python3 test_bc038_v0_2.py
python3 bc038_analyze.py .
sha256sum -c SHA256SUMS
```

No credential is required for these checks. Model calls are not part of the local test.
