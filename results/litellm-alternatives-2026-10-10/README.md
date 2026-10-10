# LiteLLM alternatives (bc-114)

Evidence for the BenchClaw article [LiteLLM Alternatives After the PyPI Attack: What We Could Verify](https://benchclaw.io/litellm-alternatives/).

**No gateway was installed, run or called, and no account was opened.** The script reads public pages and APIs only.

## What this checks

1. The March 2026 LiteLLM supply-chain incident, from the two primary sources (LiteLLM's notice and PyPI's incident report), PyPI's own JSON API (are the compromised releases still there?) and the OSV record PYSEC-2026-2.
2. Eight open-source gateways on GitHub: licence, language, archived flag, last commit, latest release of the main product, stable releases in the last 90 days, and published security advisories (LiteLLM, Bifrost, MLflow, Kong, Envoy AI Gateway, Portkey's gateway, Helicone, TensorZero).
3. Claims in Google's AI Overview for `litellm alternatives`, checked against GitHub, Palo Alto Networks' release on Portkey, and Bifrost's and MLflow's own comparison pages, which also say what those vendors claim about LiteLLM.

## Method

- `check_litellm_alternatives.py`: Python standard library only. Makes about 40 GitHub requests, so set `GITHUB_TOKEN` (unauthenticated GitHub allows 60 an hour and the script will return `error: 403` rows). Reads `google-ai-overview-litellm-alternatives-2026-10-10.md` from this directory.
- Dates use a fixed cut-off, `--as-of 2026-10-10T16:00:00Z`, so runs agree even though LiteLLM releases almost daily. Page text and advisories are read live. Two runs on 2026-10-10 were byte-identical.
- Release counts use each project's main tag series (`vX.Y.Z`; `transports/vX.Y.Z` for Bifrost, which tags about 15 packages per release; `X.Y.Z` for Kong), pre-releases excluded.
- `litellm-alternatives-2026-10-10.json`: the raw, unedited output.

## Limits

Advisory counts show what a project publishes through GitHub security advisories. They depend on project size and disclosure habits and are not a safety ranking: Kong publishes none on GitHub, which does not mean it has no vulnerabilities. Latency and throughput numbers in the article are the vendors' own claims, quoted with their conditions; we ran no gateway. PyPI and LiteLLM give different exposure windows for the same incident and we report both.

## Reproduce

```bash
export GITHUB_TOKEN=...   # any token, read-only
python3 check_litellm_alternatives.py > mine.json     # about 30 seconds
```
