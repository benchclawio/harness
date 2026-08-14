# AI agent evaluation tools benchmark (bc-038)

Evidence for the BenchClaw article [AI Agent Evaluation Tools: We Measured How Often They Are Wrong](https://benchclaw.io/ai-agent-evaluation-tools/).

## Study

- Run date: 2026-08-14
- Corpus: 70 matched cases, 35 labelled wrong and 35 labelled correct
- Repeats: 3 per case and arm
- Arms: naive GPT judge, Phoenix 3.4.0, DeepEval 4.1.8, Opik 2.2.28
- Judge: `gpt-4o-2024-08-06`, temperature 0
- Total: 840 evaluations, 1,061 API calls, $2.1308 measured model cost

The corpus contains 34 constructed wrong outputs and one organic model failure. It tests evaluator behaviour, not the prevalence of agent defects in production. Every Wilson 95% interval overlaps, so the study does not rank the tools.

Four controls originally labelled correct contain an additional inventory defect. The analysis publishes both the frozen labels and a sensitivity analysis excluding those disputed controls. False-pass rates are unaffected.

## Verify locally

No API key or framework installation is required.

```bash
sha256sum -c SHA256SUMS
python3 bc038_verify.py
```

Expected case-level false-pass / false-fail counts:

```text
naive       5/35  11/35
phoenix     5/35  10/35
deepeval    8/35   5/35
opik        0/35  16/35
```

## Contents

- `bc038-rerun-manifest-v0.2.0.json`: protocol frozen before the rerun
- `bc038-corpus-v0.2.0.json`: hand-verified corpus
- `bc038-eval-*-v0.2.0.jsonl`: raw evaluator records
- `bc038-ledger-*-v0.2.0.jsonl`: prompt-free API usage ledgers
- `bc038-analysis-v0.2.0-2026-08-14.json`: full analysis
- `bc038_verify.py`: zero-dependency headline verifier
- `bc038_analyze_v0_2.py`: full analysis script
- `bc038_arms_v0_2.py`, `bc038_openai_ledger_proxy.py`: run code
- `bc038_repair_corpus.py`: v0.2.0 corpus construction
- `freeze-*.txt`: environment locks for each arm

The pre-registration and corpus specification are in [`methodology/`](../methodology/).
