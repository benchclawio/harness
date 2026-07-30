# BenchClaw harness

The BenchClaw measurement and evidence layer for reproducible AI-agent framework benchmarks.

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21703726.svg)](https://doi.org/10.5281/zenodo.21703726)

## What this is

BenchClaw publishes independent, reproducible benchmarks of AI-agent frameworks. This repository contains:

- **`src/benchclaw_harness/`** — the core harness: runner, scorer, redaction, paired analysis, and manifests
- **`adapters/`** — subject workers for LangGraph 1.2.9 and Pydantic AI Slim 2.13.0; each runs in its own isolated Python environment
- **`task-suites/`** — frozen task definitions used in published runs
- **`tasks/`** — fixture task definitions for local testing without API calls
- **`config/`** — pilot run configurations

## Run the fixture pilot (no API key needed)

The fixture pilot uses deterministic stubs instead of real framework calls. It verifies the pipeline end-to-end with zero cost.

```bash
pip install -e .
PYTHONPATH=src python3 -m benchclaw_harness run \
  --config config/fixture-pilot-v1.json \
  --output artifacts/fixture-pilot
```

Verify an existing bundle:

```bash
PYTHONPATH=src python3 -m benchclaw_harness verify artifacts/fixture-pilot
```

Run the test suite:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## Run against real frameworks

Real-framework adapters require isolated Python environments with the exact locked dependency sets. See the BenchClaw methodology for environment setup instructions.

Each live run requires:
1. A credential file at `~/.openclaw/credentials/openai-api-key` (or equivalent; never committed)
2. Isolated `.venvs/langgraph/` and `.venvs/pydantic-ai/` environments at the repo root
3. Explicit per-call approval under BenchClaw's paid-call policy

After those isolated environments are installed, their fake-mode adapter contracts can be checked without an API call:

```bash
PYTHONPATH=src python3 adapters/test_adapters.py
```

## Output format

Each run produces a directory with:

| File | Contents |
|---|---|
| `inputs/config.json` | Frozen run configuration |
| `inputs/task-suite.json` | Frozen task suite used |
| `events.jsonl` | One terminal event per subject/task/run |
| `analysis.json` | Subject summaries and paired comparisons |
| `manifest.json` | SHA-256 digests and analysis settings |

## Security

- API keys are read from a local credential file at runtime; they are never written to harness output or committed to this repository
- The `.gitignore` excludes `*.jsonl`, `.venvs/`, `.wheelhouse/`, and common credential file patterns
- Fake-mode workers explicitly blank credentials and block outbound network connections

## Published results

| Study | Evidence | Article |
|---|---|---|
| LangGraph 1.2.9 vs Pydantic AI 2.13.0, 160 runs | [raw data, analysis, manifest, and checksums](results/langgraph-vs-pydantic-ai-2026-07-25/) | [Benchmark report](https://benchclaw.io/langgraph-vs-pydantic-ai-benchmark/) |
| gpt-4o vs gpt-4o-mini tool calling, 80 pilot runs | [raw data, analyses, manifests, and checksums](results/gpt-4o-vs-gpt-4o-mini-tool-calling-2026-07-24/) | [Pilot report](https://benchclaw.io/pilot-langgraph-pydantic-ai/) |
| Pydantic AI 2.18.0 review, 80 runs | [raw data, analysis, and manifest](results/pydantic-ai-review-2.18.0-gpt-4o-2026-07-27/) | [Review](https://benchclaw.io/pydantic-ai-review/) |
| Pydantic AI 2.18.0 Skills verification | [scripts and outputs](results/pydantic-ai-skills-2.18.0-2026-07-27/) | [Skills guide](https://benchclaw.io/pydantic-ai-skills/) |
| LangChain/LangGraph dependency verification | [scripts and outputs](results/langchain-vs-langgraph-2026-07-28/) | [Comparison](https://benchclaw.io/langchain-vs-langgraph/) |

The [BenchClaw methodology](https://benchclaw.io/methodology/) defines the evidence standard, scoring rules, failure taxonomy, and statistical plan. Published JSONL files are sanitized evidence exports; local, unreviewed run artifacts remain ignored by default.

## Reproducing and verifying

The zero-cost fixture pilot is the quickest way to verify the complete runner-to-manifest pipeline:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
PYTHONPATH=src .venv/bin/python -m benchclaw_harness run \
  --config config/fixture-pilot-v1.json \
  --output artifacts/fixture-pilot
PYTHONPATH=src .venv/bin/python -m benchclaw_harness verify \
  artifacts/fixture-pilot
```

For a published study, verify the files against its `SHA256SUMS`, then inspect the frozen task suite, manifest, analysis, and raw JSONL records together. Historical paid runs are evidence archives: rerunning them requires the named model, credentials, pinned framework versions, and may not reproduce provider latency because network and provider conditions change.

## Citation

Use GitHub's **Cite this repository** control or the metadata in [`CITATION.cff`](CITATION.cff). Versioned releases are archived with Zenodo; the release-specific DOI should be preferred when citing an exact version.

- **Release `v0.2.0`:** [10.5281/zenodo.21703726](https://doi.org/10.5281/zenodo.21703726)
- **All versions:** [10.5281/zenodo.21703725](https://doi.org/10.5281/zenodo.21703725)

## License

Licensed under the [Apache License 2.0](LICENSE).
