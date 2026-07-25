"""
BenchClaw real-framework pilot — Pydantic AI 2.13.0 subject worker.

Runs in: projects/benchclaw/.venvs/pydantic-ai
Protocol: reads one JSON run request from stdin; writes one JSON result to stdout.

Modes:
  fake  — deterministic FunctionModel replay; no network, no credentials
  live  — real OpenAI API call via OpenAIChatModel; requires OPENAI_API_KEY in env
"""

from __future__ import annotations

import json
import os
import socket as _socket
import sys
import time
from pathlib import Path
from typing import Any

# Read stdin early so mode is known before applying network block.
_RAW_REQUEST = sys.stdin.read()
_MODE = json.loads(_RAW_REQUEST).get("mode", "fake")

# --- telemetry off -----------------------------------------------------------
os.environ["LOGFIRE_SEND_TO_LOGFIRE"] = "false"
os.environ["LOGFIRE_TOKEN"] = ""

# In fake mode, blank any credentials so they can't be used accidentally.
if _MODE != "live":
    os.environ["OPENAI_API_KEY"] = ""
    os.environ["ANTHROPIC_API_KEY"] = ""

# --- block outbound network in fake mode only --------------------------------
if _MODE != "live":
    def _no_connect(self, address):
        raise ConnectionRefusedError(f"worker_pydantic_ai: network blocked — {address}")
    _socket.socket.connect = _no_connect

# --- shared tools (stdlib only) ----------------------------------------------
sys.path.insert(0, str(Path(__file__).parent))
from shared_tools import (  # noqa: E402
    ToolContractError,
    ToolRuntime,
    score_run,
    fake_tool_args,
    fake_final_output,
    FAKE_TOKENS_IN_PER_REQUEST,
    FAKE_TOKENS_OUT_PER_REQUEST,
)

# --- framework imports -------------------------------------------------------
from pydantic_ai import Agent
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    RequestUsage,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.result import UsageLimits

# OpenAI model pricing (USD per token in, per token out)
_MODEL_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o-mini":       (0.150 / 1_000_000, 0.600 / 1_000_000),
    "gpt-4o":            (2.500 / 1_000_000, 10.000 / 1_000_000),
    "gpt-4o-2024-08-06": (2.500 / 1_000_000, 10.000 / 1_000_000),
    "gpt-4.1-mini":      (0.400 / 1_000_000,  1.600 / 1_000_000),
}
_DEFAULT_PRICING = (2.500 / 1_000_000, 10.000 / 1_000_000)

def _cost_usd(model_id: str, tokens_in: int, tokens_out: int) -> float:
    price_in, price_out = _MODEL_PRICING.get(model_id, _DEFAULT_PRICING)
    return round(tokens_in * price_in + tokens_out * price_out, 8)


# ---------------------------------------------------------------------------
# Dynamic tool builder
# ---------------------------------------------------------------------------

_PY_TYPES = {
    "string": "str",
    "number": "float",
    "integer": "int",
    "boolean": "bool",
}


def _build_pai_tools(task: dict[str, Any], runtime: ToolRuntime, agent: Agent) -> None:
    """Register tool functions on the agent, dispatching through runtime."""
    for tool_def in task["tools"]:
        name = tool_def["name"]
        description = tool_def["description"]
        schema = tool_def["input_schema"]
        props = schema.get("properties", {})
        param_names = sorted(props.keys())

        param_str = ", ".join(
            f"{p}: {_PY_TYPES.get(props[p].get('type', 'string'), 'str')}"
            for p in param_names
        )
        args_dict = "{" + ", ".join(f'"{p}": {p}' for p in param_names) + "}"
        code = (
            f"def {name}({param_str}) -> str:\n"
            f"    result = _dispatch({args_dict})\n"
            f"    return json.dumps(result)\n"
        )
        ns: dict[str, Any] = {
            "json": json,
            "_dispatch": (lambda n: lambda args: runtime.call(n, args))(name),
        }
        exec(code, ns)
        fn = ns[name]
        fn.__doc__ = description
        agent.tool_plain(fn)


# ---------------------------------------------------------------------------
# Fake model (deterministic, no network)
# ---------------------------------------------------------------------------

def _build_fake_fn(task: dict[str, Any], fake_mode: str, token_tracker: dict):
    reference_trace = task["reference_trace"]

    def fake_fn(messages, info):
        tool_return_count = sum(
            1 for m in messages
            if isinstance(m, ModelRequest)
            for p in m.parts
            if isinstance(p, ToolReturnPart)
        )
        token_tracker["requests"] += 1
        token_tracker["tokens_in"] += FAKE_TOKENS_IN_PER_REQUEST
        token_tracker["tokens_out"] += FAKE_TOKENS_OUT_PER_REQUEST

        budget_exhausted = fake_mode == "budget_exhausted"
        more_calls = tool_return_count < len(reference_trace) or budget_exhausted

        if more_calls and tool_return_count <= task["limits"]["tool_calls"]:
            t_name, t_args = fake_tool_args(task, fake_mode, tool_return_count)
            return ModelResponse(
                parts=[ToolCallPart(t_name, t_args)],
                usage=RequestUsage(
                    input_tokens=FAKE_TOKENS_IN_PER_REQUEST,
                    output_tokens=FAKE_TOKENS_OUT_PER_REQUEST,
                ),
            )
        else:
            return ModelResponse(
                parts=[TextPart(fake_final_output(task, fake_mode))],
                usage=RequestUsage(
                    input_tokens=FAKE_TOKENS_IN_PER_REQUEST,
                    output_tokens=FAKE_TOKENS_OUT_PER_REQUEST,
                ),
            )

    return fake_fn


# ---------------------------------------------------------------------------
# Agent runners
# ---------------------------------------------------------------------------

def run_with_fake_model(task: dict[str, Any], fake_mode: str) -> dict[str, Any]:
    runtime = ToolRuntime(task)
    token_tracker = {"requests": 0, "tokens_in": 0, "tokens_out": 0}

    fake_fn = _build_fake_fn(task, fake_mode, token_tracker)

    agent: Agent[None, str] = Agent(
        FunctionModel(fake_fn),
        output_type=str,
        retries=0,
    )
    _build_pai_tools(task, runtime, agent)

    result = agent.run_sync(
        task["prompt"],
        usage_limits=UsageLimits(request_limit=task["limits"]["model_requests"]),
    )

    score = score_run(task, runtime, result.output)
    usage = result.usage
    return {
        "tokens_in": usage.input_tokens or token_tracker["tokens_in"],
        "tokens_out": usage.output_tokens or token_tracker["tokens_out"],
        "model_requests": usage.requests,
        "cost_usd": 0.0,
        "score": score,
        "output": result.output,
    }


def run_with_live_model(task: dict[str, Any], api_key: str, model_id: str) -> dict[str, Any]:
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider
    from pydantic_ai.models.openai import OpenAIChatModelSettings

    runtime = ToolRuntime(task)

    model = OpenAIChatModel(
        model_id,
        provider=OpenAIProvider(api_key=api_key),
    )
    agent: Agent[None, str] = Agent(model, output_type=str, retries=0)
    _build_pai_tools(task, runtime, agent)

    model_settings = OpenAIChatModelSettings(
        temperature=0,
        parallel_tool_calls=False,
        max_tokens=task["limits"]["output_tokens"],
    )

    result = agent.run_sync(
        task["prompt"],
        usage_limits=UsageLimits(request_limit=task["limits"]["model_requests"]),
        model_settings=model_settings,
    )

    score = score_run(task, runtime, result.output)
    usage = result.usage
    tokens_in = usage.input_tokens or 0
    tokens_out = usage.output_tokens or 0
    return {
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "model_requests": usage.requests,
        "cost_usd": _cost_usd(model_id, tokens_in, tokens_out),
        "score": score,
        "output": result.output,
    }


# ---------------------------------------------------------------------------
# Failure classification
# ---------------------------------------------------------------------------

def _classify_tool_contract_error(msg: str) -> str:
    if "budget exhausted" in msg:
        return "loop_or_budget_exhausted"
    return "malformed_tool_call"


def _sanitize(msg: str) -> str:
    return str(msg)[:240]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    request = json.loads(_RAW_REQUEST)
    task = request["task"]
    mode = request.get("mode", "fake")
    fake_mode = request.get("fake_mode", "correct")
    model_id = request.get("model_id", "gpt-4o-mini")

    wall_start = time.monotonic()
    try:
        if mode == "live":
            api_key = os.environ.get("OPENAI_API_KEY", "")
            if not api_key:
                raise RuntimeError("OPENAI_API_KEY is not set")
            outcome = run_with_live_model(task, api_key, model_id)
        elif mode == "fake":
            outcome = run_with_fake_model(task, fake_mode)
        else:
            raise NotImplementedError(f"mode {mode!r} not supported")

        wall_time = time.monotonic() - wall_start
        score = outcome["score"]

        if not score["completed"]:
            errors = score["errors"]
            has_forbidden = any("forbidden" in e for e in errors)
            has_json_error = any("valid JSON" in e for e in errors)
            if has_forbidden:
                failure_type = "policy_blocked"
            elif has_json_error:
                failure_type = "invalid_final_answer"
            else:
                failure_type = "invalid_final_answer"
            first_error = errors[0] if errors else "score failure"

            result: dict[str, Any] = {
                "status": "failure",
                "completed": False,
                "metrics": {
                    "tokens_in": outcome["tokens_in"],
                    "tokens_out": outcome["tokens_out"],
                    "cost_usd": outcome["cost_usd"],
                    "wall_time_s": round(wall_time, 4),
                    "tool_calls": score["tool_calls"],
                },
                "failure": {
                    "type": failure_type,
                    "stage": "scoring",
                    "message_sanitized": _sanitize(first_error),
                },
                "score": score,
            }
        else:
            result = {
                "status": "success",
                "completed": True,
                "metrics": {
                    "tokens_in": outcome["tokens_in"],
                    "tokens_out": outcome["tokens_out"],
                    "cost_usd": outcome["cost_usd"],
                    "wall_time_s": round(wall_time, 4),
                    "tool_calls": score["tool_calls"],
                },
                "failure": None,
                "score": score,
            }

    except ToolContractError as exc:
        wall_time = time.monotonic() - wall_start
        result = {
            "status": "failure",
            "completed": False,
            "metrics": {
                "tokens_in": None,
                "tokens_out": None,
                "cost_usd": 0.0,
                "wall_time_s": round(wall_time, 4),
                "tool_calls": None,
            },
            "failure": {
                "type": _classify_tool_contract_error(str(exc)),
                "stage": "tool_execution",
                "message_sanitized": _sanitize(str(exc)),
            },
            "score": None,
        }

    except json.JSONDecodeError as exc:
        wall_time = time.monotonic() - wall_start
        result = {
            "status": "failure",
            "completed": False,
            "metrics": {
                "tokens_in": None,
                "tokens_out": None,
                "cost_usd": 0.0,
                "wall_time_s": round(wall_time, 4),
                "tool_calls": None,
            },
            "failure": {
                "type": "invalid_final_answer",
                "stage": "output_parsing",
                "message_sanitized": _sanitize(str(exc)),
            },
            "score": None,
        }

    except Exception as exc:
        wall_time = time.monotonic() - wall_start
        result = {
            "status": "error",
            "completed": False,
            "metrics": {
                "tokens_in": None,
                "tokens_out": None,
                "cost_usd": 0.0,
                "wall_time_s": round(wall_time, 4),
                "tool_calls": None,
            },
            "failure": {
                "type": "unhandled_exception",
                "stage": "adapter",
                "message_sanitized": _sanitize(type(exc).__name__),
            },
            "score": None,
        }

    sys.stdout.write(json.dumps(result) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
