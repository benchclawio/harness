# bc-040 static audit — `openai-agents` 0.21.1

Performed 2026-08-17, locally, **without executing the package**. Wheel unpacked and read
only. Same treatment that accepted LangGraph 1.2.9 and pydantic-ai-slim 2.13.0 and rejected
CrewAI 1.15.5.

## Provenance

| | |
|---|---|
| artifact | `openai_agents-0.21.1-py3-none-any.whl` |
| sha256 | `47cdc36c70aa1c0bd4337d040b605b1ea4ac598f178b59f4040208884785f0d0` |
| verified | matches PyPI's published digest exactly |
| sdist sha256 | `7d6519bed92542b2a7160cd50edca0721c64d5f06616d85c6de477f237b8423c` |
| released | 2026-08-16 |
| contents | 305 Python files, 317 total |

Pure `py3-none-any` wheel. **No `.pth` files, no compiled `.so`, no install-time hooks.**
Nothing runs at install.

Declared dependencies: `openai>=3.0.0,<4`, `pydantic>=2.12.2,<3`, `mcp>=1.19.0,<3`,
`griffelib>=2,<3`, `requests>=2,<3`, `websockets>=15.0,<17`, `typing-extensions>=4.12.2,<5`.

## Verdict: **SAFE — with isolation controls**

No module-level network calls anywhere in the package. No import-time file or network side
effects in `agents/__init__.py`. No obfuscation, no dynamic import of remote code, no
`pickle.loads`/`marshal.loads` on untrusted input.

Four things must be controlled, and two of them affect the measurement, not just safety.

### 1. Tracing uploads to OpenAI by default — MUST disable

`agents/tracing/processors.py:45` posts to `https://api.openai.com/v1/traces/ingest`, and
authenticates with `OPENAI_API_KEY` (`processors.py:108`). Worse,
`agents/run_config.py:54` defaults `OPENAI_AGENTS_TRACE_INCLUDE_SENSITIVE_DATA` to **`"true"`**
— so out of the box the SDK ships task prompts and tool payloads to OpenAI's trace store.

Disabled three ways, belt and braces: `OPENAI_AGENTS_DISABLE_TRACING=true`
(`agents/tracing/provider.py:348`), `set_tracing_disabled(True)`, and
`RunConfig(tracing_disabled=True)`.

This is also a **publishable finding**, not merely a control. LangGraph uploads nothing by
default; the OpenAI Agents SDK uploads traces including sensitive data by default. That is a
real difference between the arms and belongs on the page. It is also an unmeasured network
round trip per run — leaving it on would have quietly inflated the subject's latency.

### 2. The SDK defaults to the Responses API — MUST force parity

`agents/models/_openai_shared.py:11` sets `_use_responses_by_default = True`. Our LangGraph
arm goes through Chat Completions. Two arms on two different endpoints is a confound: they
differ in latency and in token accounting, and the result would measure the endpoints rather
than the frameworks.

Forced to `set_default_openai_api("chat_completions")` so both arms hit the same endpoint.
**This must be disclosed on the page** — it is a deliberate deviation from the SDK's default
configuration, made for comparability.

### 3. Do not import the experimental Codex extension

`agents/extensions/experimental/codex/exec.py:220` copies the entire `os.environ` into a
spawned subprocess, and `codex_tool.py:620-624` reads `CODEX_API_KEY` and `OPENAI_API_KEY`.
Opt-in and irrelevant to the benchmark, but it is the widest credential surface in the
package. Not imported.

### 4. Do not use `agents.sandbox`

`agents/sandbox/` wraps Docker `exec` for agent code execution (`sandboxes/docker.py`,
including an `rm -rf` at line 501, correctly parameterised with `shell=False`). Opt-in,
unused, and moot anyway — Hetzner Cloud has no KVM.

### Not a defect, but noted

`agents/models/default_models.py:103` defaults to `gpt-5.6-luna` when no model is given. We
pin `gpt-4o` explicitly, so this never applies.

## Controls applied for the run

- Network egress restricted to `api.openai.com`
- `OPENAI_AGENTS_DISABLE_TRACING=true`, plus the two in-code disables
- `set_default_openai_api("chat_completions")`
- Isolated, pip-less, hash-verified environment, one per arm
- Codex extension and sandbox module never imported
- Credential from the `600` file, never written to the run output

**Approved for installation at sha256 `47cdc36c…f0d0` under these controls.**
