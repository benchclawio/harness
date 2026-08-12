# Langfuse vs Arize Phoenix capture-completeness study

Evidence for BenchClaw's LLM observability tools benchmark, run 2026-08-12.

## Result

This is a null result on the primary outcome. Langfuse and Phoenix each captured every
scored signal in a scripted agent-shaped workload:

| Signal | Issued per tool | Langfuse | Phoenix |
|---|---:|---:|---:|
| LLM spans | 200 | 200/200 | 200/200 |
| Tool spans | 140 | 140/140 | 140/140 |
| Retrieval spans | 60 | 60/60 | 60/60 |
| All spans | 400 | 400/400 | 400/400 |
| Parent-child edges | 180 | 180/180 | 180/180 |
| Injected-error records | 40 | 40/40 | 40/40 |

No missing spans, incorrect parents, missing error records or duplicates were observed. The
Wilson 95% lower bound for 400/400 is 0.990488, so the supported claim is “no drop observed,”
not “perfect capture proven.”

Bootstrap percentile intervals on mean wall-time difference against the uninstrumented
control both crossed zero: Langfuse −0.2544 seconds, 95% CI [−1.1465, +0.7616]; Phoenix
+1.4329 seconds, 95% CI [−0.0843, +3.1475]. Neither tool wins on overhead in this study.

## Pins

- 20 runs per arm: uninstrumented control, Langfuse, Phoenix; 60 runs total
- 20 spans per run: 10 LLM, 7 tool, 3 retrieval; 9 parent-child edges; 2 injected errors
- Model: `gpt-4o`, temperature 0; 540 provider requests
- Langfuse server: 4.10.0; Python SDK: 4.14.4
- Arize Phoenix: 20.1.0; Phoenix client: 3.1.0; Phoenix OTEL: 0.17.1
- Host: Hetzner cpx41, 8 vCPU / 16 GB, Ubuntu 24.04.4, `ash-dc1`
- Suite SHA-256: `423980f8aa741c0c88dd82c1ba5fa0c09a9f25c3a51291e63c51389fd956ca10`
- Total model spend: $0.099; server spend: approximately €0.06

The Python packages were checked against PyPI on 2026-08-12: Langfuse SDK 4.14.4 and Arize
Phoenix 20.1.0 were current. The measured Langfuse server remains pinned to 4.10.0.

## The methodological finding

Two reader defects nearly produced false accusations against Langfuse:

1. Requesting `fields=metadata` made the default `level` projection null. A reader using one
   projection reported 0/2 injected errors even though both were present. The corrected
   reader joins two API projections on observation id.
2. The observations endpoint is cursor-paginated and silently ignored `page`. A page-number
   reader repeatedly collected the first 100 records and would report 25% capture against
   400 issued spans. One `limit=500` request returned all scored records.

Both bad readers passed a two-span “did anything arrive?” probe. The reusable control is a
**Counted Positive Control**: assert a known count at production-like volume, not merely the
presence of one known span.

## Files

| Path | Contents |
|---|---|
| `bc039-scored-2026-08-12-raw.jsonl` | 60 per-run records, including issued counts and timings |
| `bc039-scored-2026-08-12-capture-final.json` | corrected capture, nesting and error results |
| `bc039-overhead.json` | fixed-seed bootstrap intervals against control |
| `bc039-results-2026-08-12.md` | result narrative and threats to validity |
| `methodology/bc039-protocol-v0.1.0.md` | protocol frozen before measurement, with deviations recorded |
| `methodology/bc039-workload-v0.1.0.json` | frozen workload and exact ground truth |
| `adapters/` | runner, tool wiring, raw-export readers, scorer and 40-check offline test |
| `scripts/bc039_workload.py` | byte-stable workload generator |
| `provenance.json`, `pipfreeze.txt`, `requirements-bc039.txt` | environment and version pins |
| `SHA256SUMS` | file-integrity manifest |

## Verify without an API key

The offline test uses only Python's standard library. It regenerates the workload logic and
deliberately simulates missing spans, flattened nesting, lost errors, duplicates and token
mismatches.

```bash
python3 adapters/test_bc039.py
sha256sum -c SHA256SUMS
```

Expected JSON result: `"passed": 40`, `"failed": 0`.

Re-reading Langfuse or Phoenix requires the original self-hosted backends and credentials.
The published final JSON is the corrected API read-back from those live stores; the raw
workload JSONL is sufficient to inspect every issued denominator and timing.

## Limits

Manual instrumentation was used in both arms; auto-instrumentation was disabled. The study
does not measure dashboard quality, alerting, RBAC, compliance, support, retention, SaaS
latency or long-horizon traces. Phoenix's store retained 28 pre-run spans, but scored records
were isolated by `(run_id, step_index)` and all 400 scored spans were accounted for.
