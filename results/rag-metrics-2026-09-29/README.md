# RAG evaluation metrics: Ragas 0.4.3 vs DeepEval 4.2.6 (source inspection)

Evidence for the BenchClaw article "RAG Evaluation Metrics" (bc-098). Run date: 2026-09-29.

This is a **source inspection**, not a model benchmark. No LLM was called, no score was measured on a real RAG system, and no number here is a performance figure. The script reads the shipped code of two wheels, prints the scoring lines, and runs the pure-Python scoring functions on **hand-built verdict lists** (not model output) to show what each library returns on edge cases.

## Inputs (hash-verified by the script)

| Package | Version | Released | Wheel SHA-256 |
|---|---|---|---|
| `ragas` | 0.4.3 | 2026-01-13 | `ef1d75f674c294e9a6e7d8e9ad261b6bf4697dad1c9cbd1a756ba7a6b4849a38` |
| `deepeval` | 4.2.6 | 2026-09-24 | `d3af4b9e36d46ad6c7fa640a423ee566dcb7e05f3ccc72516a821825e5d4fb4f` |

Both were the latest releases on PyPI on 2026-09-29. Hashes match the values PyPI publishes.

## Run it

```
python3 inspect_rag_metrics.py ragas-0.4.3-py3-none-any.whl deepeval-4.2.6-py3-none-any.whl
```

Standard library only (Python 3.14.4 used). The script aborts if either wheel hash differs. It extracts function source from the wheels with `ast` and executes only the pure-Python scoring functions, with a minimal stand-in for `numpy.nan`/`numpy.isnan` and for DeepEval's `Verdict` enum. The embedding-based part of Ragas answer relevancy needs `numpy` and an embedding model, so it is **printed and asserted, not executed**.

## Files

| File | SHA-256 |
|---|---|
| `inspect_rag_metrics.py` | `89fe89c7bfc578223dd04d974c42f4d45b91db2628b9dfab1d4c5948d4b57bed` |
| `inspect-output-2026-09-29.txt` | `bbf80bd1321af5e9eff9e25dac692dc0cfdde9000470c1f9b92c0f2c7b1e9bdd` |

The script was executed three times on 2026-09-29; the three outputs were byte-identical.

## What it shows

1. Ragas answer relevancy scores `cosine_sim.mean() * int(not all_noncommittal)` from an embedding model and 3 generated questions; it reads only `user_input` and `response`. DeepEval's answer relevancy has no embedding code (0 occurrences of "embed") and counts the share of statements judged relevant, with borderline verdicts passing.
2. With zero extracted statements or claims, Ragas faithfulness and context recall return `nan`; DeepEval faithfulness and answer relevancy return 1 and contextual recall returns 0.
3. DeepEval faithfulness on verdicts yes, yes, borderline, no scores 0.75 by default and 0.5 with `penalize_ambiguous_claims=True`.
4. Both libraries compute context precision with the same weighted-precision-at-k formula; on the three ranked lists tested they return identical values.
5. Required inputs per metric. Faithfulness and answer relevancy need no reference answer; context precision and recall need one in both libraries.

## Not tested

Actual scores on any RAG pipeline, judge-model variance, embedding-model sensitivity, Ragas metrics other than the four above, DeepEval's `hybrid` "System One" evaluation mode, and other frameworks (TruLens, Evidently, LangSmith, Phoenix).
