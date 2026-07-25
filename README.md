# BenchClaw harness

The BenchClaw measurement and evidence layer for reproducible AI-agent framework benchmarks.

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

See [benchclaw.io](https://benchclaw.io) for published benchmarks, methodology, and sanitized raw result files.
