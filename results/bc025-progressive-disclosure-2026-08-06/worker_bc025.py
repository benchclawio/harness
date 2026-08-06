#!/usr/bin/env python3
"""bc-025 worker: one run of one cell of the progressive-disclosure benchmark.

Reads a JSON request on stdin and writes one JSON result on stdout.

    {"task": {...}, "capabilities": [...], "arm": "always_on"|"deferred",
     "path": "chat"|"responses", "model_id": "gpt-4o", "mode": "live"|"fake"}

All 20 capabilities are registered in every cell. `arm` changes only whether they are
marked `defer_loading`; `path` changes only whether tool search executes server-side
(OpenAI Responses) or through the local fallback toolset (OpenAI Chat Completions).

Token counts come from provider-reported usage. They are never inferred from
`AgentInfo.function_tools`, which lists a deferred tool both before and after load and
therefore cannot answer "was this schema in the prompt?" (verified 2026-07-27, still true
in 2.24.0).
"""

from __future__ import annotations

import json
import os
import socket as _socket
import sys
import time
from typing import Any


_ALLOWED_HOST_SUFFIX = ("api.openai.com",)


def _guard_network() -> None:
    """Block every outbound connection except the OpenAI API host."""
    real_connect = _socket.socket.connect

    def _checked_connect(self, address):
        host = address[0] if isinstance(address, tuple) else ""
        if isinstance(host, str) and not host.replace(".", "").isdigit():
            if not host.endswith(_ALLOWED_HOST_SUFFIX):
                raise OSError(f"blocked outbound connection to {host}")
        return real_connect(self, address)

    _socket.socket.connect = _checked_connect


_guard_network()

from pydantic_ai import Agent  # noqa: E402
from pydantic_ai.result import UsageLimits  # noqa: E402
from pydantic_ai.toolsets import FunctionToolset  # noqa: E402
from pydantic_ai.toolsets.deferred_loading import DeferredLoadingToolset  # noqa: E402


_MODEL_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.500 / 1_000_000, 10.000 / 1_000_000),
    "gpt-4o-mini": (0.150 / 1_000_000, 0.600 / 1_000_000),
}
_DEFAULT_PRICING = (2.500 / 1_000_000, 10.000 / 1_000_000)

_PY_TYPES = {"string": "str", "number": "float", "integer": "int", "boolean": "bool"}


def _cost_usd(model_id: str, tokens_in: int, tokens_out: int) -> float:
    price_in, price_out = _MODEL_PRICING.get(model_id, _DEFAULT_PRICING)
    return round(tokens_in * price_in + tokens_out * price_out, 8)


# ---------------------------------------------------------------------------
# Deterministic capability implementations
# ---------------------------------------------------------------------------

def _dispatch(cap: dict[str, Any], args: dict[str, Any]) -> Any:
    name = cap["name"]
    fixture = cap["fixture"]

    if name == "currency_convert":
        key = f"{args['from_currency']}:{args['to_currency']}"
        if key not in fixture:
            return {"error": "unknown_currency_pair"}
        return {
            "from_currency": args["from_currency"],
            "to_currency": args["to_currency"],
            "rate": fixture[key],
            "converted": round(float(args["amount"]) * fixture[key], 4),
        }

    if name == "carrier_rate":
        key = f"{args['origin']}:{args['destination']}"
        if key not in fixture:
            return {"error": "unknown_lane"}
        entry = fixture[key]
        return {"quote": round(entry["base"] + entry["per_kg"] * float(args["weight_kg"]), 2)}

    if name == "insurance_premium":
        value = float(args["declared_value"])
        for low, high, premium in fixture["bands"]:
            if low <= value < high:
                return {"declared_value": value, "premium": premium}
        return {"error": "value_out_of_range"}

    # Every remaining capability is a single-key record lookup.
    lookup = args[sorted(args)[0]] if len(args) == 1 else args[cap["input_schema"]["required"][0]]
    if lookup not in fixture:
        return {"error": "not_found"}
    return fixture[lookup]


def _build_toolset(capabilities: list[dict[str, Any]], calls: list[str]) -> FunctionToolset:
    toolset: FunctionToolset = FunctionToolset()
    for cap in capabilities:
        name = cap["name"]
        props = cap["input_schema"].get("properties", {})
        param_names = sorted(props)
        param_str = ", ".join(
            f"{p}: {_PY_TYPES.get(props[p].get('type', 'string'), 'str')}" for p in param_names
        )
        args_dict = "{" + ", ".join(f'"{p}": {p}' for p in param_names) + "}"
        code = (
            f"async def {name}({param_str}) -> str:\n"
            f"    _record('{name}')\n"
            f"    return json.dumps(_call({args_dict}))\n"
        )
        ns: dict[str, Any] = {
            "json": json,
            "_call": (lambda c: lambda args: _dispatch(c, args))(cap),
            "_record": calls.append,
        }
        exec(code, ns)
        fn = ns[name]
        fn.__doc__ = cap["description"]
        toolset.add_function(fn)
    return toolset


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _strip_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _score(task: dict[str, Any], output: str, calls: list[str]) -> dict[str, Any]:
    expected = task["expected_output"]
    try:
        parsed = json.loads(_strip_fences(output))
    except Exception:
        return {"exact_match": False, "parse_ok": False, "correct_tool_used": False}

    exact = parsed == expected
    return {
        "exact_match": exact,
        "parse_ok": True,
        "correct_tool_used": task["target_capability"] in calls,
        "tool_calls_made": len(calls),
        "distinct_tools_called": sorted(set(calls)),
    }


def _count_search_parts(messages) -> int:
    """Count tool-search calls across both execution paths.

    `tool_kind == 'tool-search'` is the cross-provider discriminator, so this counts the
    native server-side part and the local-fallback part identically.
    """
    total = 0
    for message in messages:
        for part in getattr(message, "parts", []) or []:
            if getattr(part, "tool_kind", None) == "tool-search":
                total += 1
    return total


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def run(request: dict[str, Any]) -> dict[str, Any]:
    import httpx
    from openai import AsyncOpenAI
    from pydantic_ai.providers.openai import OpenAIProvider

    task = request["task"]
    capabilities = request["capabilities"]
    arm = request["arm"]
    path = request["path"]
    model_id = request["model_id"]
    limits = request["limits"]

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    http_client = httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=10.0), trust_env=False)
    openai_client = AsyncOpenAI(
        api_key=api_key,
        base_url="https://api.openai.com/v1",
        max_retries=0,
        timeout=90.0,
        http_client=http_client,
    )
    provider = OpenAIProvider(openai_client=openai_client)

    if path == "responses":
        from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings

        model = OpenAIResponsesModel(model_id, provider=provider)
        model_settings = OpenAIResponsesModelSettings(
            temperature=0,
            parallel_tool_calls=False,
            max_tokens=limits["output_tokens"],
        )
    elif path == "chat":
        from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings

        model = OpenAIChatModel(model_id, provider=provider)
        model_settings = OpenAIChatModelSettings(
            temperature=0,
            parallel_tool_calls=False,
            max_tokens=limits["output_tokens"],
        )
    else:
        raise RuntimeError(f"unknown path: {path}")

    calls: list[str] = []
    toolset = _build_toolset(capabilities, calls)
    if arm == "deferred":
        toolset = DeferredLoadingToolset(toolset)
    elif arm != "always_on":
        raise RuntimeError(f"unknown arm: {arm}")

    agent: Agent[None, str] = Agent(model, output_type=str, retries=0, toolsets=[toolset])

    result = agent.run_sync(
        task["prompt"],
        usage_limits=UsageLimits(
            request_limit=limits["model_requests"],
            tool_calls_limit=limits["tool_calls"],
            input_tokens_limit=limits["input_tokens"],
            output_tokens_limit=limits["output_tokens"],
            total_tokens_limit=limits["total_tokens"],
        ),
        model_settings=model_settings,
    )

    usage = result.usage
    tokens_in = usage.input_tokens or 0
    tokens_out = usage.output_tokens or 0
    return {
        "metrics": {
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "model_requests": usage.requests,
            "tool_search_calls": _count_search_parts(result.all_messages()),
            "cost_usd": _cost_usd(model_id, tokens_in, tokens_out),
        },
        "score": _score(task, result.output, calls),
        "output": result.output,
    }


def main() -> None:
    started = time.monotonic()
    try:
        request = json.loads(sys.stdin.read())
    except Exception:
        print(json.dumps({"status": "error", "error_type": "bad_request"}))
        return

    try:
        payload = run(request)
        payload["status"] = "success"
        payload["completed"] = True
    except Exception as exc:
        payload = {
            "status": "error",
            "completed": False,
            "error_type": type(exc).__name__,
            "error_class": exc.__class__.__module__ + "." + exc.__class__.__name__,
        }

    payload["wall_time_s"] = round(time.monotonic() - started, 4)
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
