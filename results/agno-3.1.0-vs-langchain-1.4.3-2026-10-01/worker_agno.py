"""
BenchClaw benchmark — Agno 3.0.1 subject worker.

Runs in: projects/benchclaw/.venvs/agno-3.0.1
Protocol: reads one JSON run request from stdin; writes one JSON result to stdout.

Modes:
  fake  — direct simulation via ToolRuntime; no network, no credentials
  live  — real OpenAI API call via Agno's OpenAIChat; requires OPENAI_API_KEY in env
"""

from __future__ import annotations

import json
import os
import socket as _socket
import sys
import time
from pathlib import Path
from typing import Any

_RAW_REQUEST = sys.stdin.read()
_MODE = json.loads(_RAW_REQUEST).get("mode", "fake")

# --- telemetry off -----------------------------------------------------------
os.environ.setdefault("AGNO_TELEMETRY", "false")
os.environ.setdefault("AGNO_MONITORING", "false")

# In fake mode, blank credentials so they can't be used accidentally.
if _MODE != "live":
    os.environ["OPENAI_API_KEY"] = ""
    os.environ["ANTHROPIC_API_KEY"] = ""

# --- block outbound network in fake mode only --------------------------------
if _MODE != "live":
    def _no_connect(self, address):
        raise ConnectionRefusedError(f"worker_agno: network blocked — {address}")
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

def _build_agno_tools(task: dict[str, Any], runtime: ToolRuntime) -> list:
    """Build Agno Function objects for each task tool with explicit JSON schemas.

    Uses skip_entrypoint_processing=True so Agno bypasses pydantic validate_call
    wrapping, which conflicts with runtime-dispatched **kwargs entrypoints.
    """
    from agno.tools.function import Function

    tools = []
    for tool_def in task["tools"]:
        name = tool_def["name"]
        description = tool_def["description"]
        schema = tool_def["input_schema"]

        # Build a **kwargs entrypoint bound to this tool's name.
        def _make_entrypoint(tool_name: str):
            def entrypoint(**kwargs: Any) -> str:
                # Filter out any framework-injected params Agno might add.
                model_args = {
                    k: v for k, v in kwargs.items()
                    if not k.startswith("_agno_") and k not in ("agent", "team", "run_context", "fc")
                }
                return json.dumps(runtime.call(tool_name, model_args))
            entrypoint.__name__ = tool_name
            return entrypoint

        fn = Function(
            name=name,
            description=description,
            parameters=schema,
            entrypoint=_make_entrypoint(name),
            skip_entrypoint_processing=True,
        )
        tools.append(fn)
    return tools


# ---------------------------------------------------------------------------
# Fake mode — direct simulation (bypasses Agno model, tests ToolRuntime +
# scoring which is the shared contract across all adapters)
# ---------------------------------------------------------------------------

def run_with_fake_model(task: dict[str, Any], fake_mode: str) -> dict[str, Any]:
    runtime = ToolRuntime(task)
    tool_call_count = 0
    token_tracker = {"tokens_in": 0, "tokens_out": 0, "requests": 0}

    while True:
        token_tracker["tokens_in"] += FAKE_TOKENS_IN_PER_REQUEST
        token_tracker["tokens_out"] += FAKE_TOKENS_OUT_PER_REQUEST
        token_tracker["requests"] += 1

        budget_exhausted = fake_mode == "budget_exhausted"
        more_calls = tool_call_count < len(task["reference_trace"]) or budget_exhausted

        if more_calls and tool_call_count <= task["limits"]["tool_calls"]:
            t_name, t_args = fake_tool_args(task, fake_mode, tool_call_count)
            runtime.call(t_name, t_args)
            tool_call_count += 1
        else:
            break

    output = fake_final_output(task, fake_mode)
    score = score_run(task, runtime, output)
    return {
        "tokens_in": token_tracker["tokens_in"],
        "tokens_out": token_tracker["tokens_out"],
        "model_requests": token_tracker["requests"],
        "cost_usd": 0.0,
        "score": score,
        "output": output,
    }


# ---------------------------------------------------------------------------
# Live mode — full Agno 3.0.1 integration
# ---------------------------------------------------------------------------

def run_with_live_model(task: dict[str, Any], api_key: str, model_id: str) -> dict[str, Any]:
    import httpx
    from agno.agent import Agent
    from agno.models.openai import OpenAIChat

    runtime = ToolRuntime(task)
    tools = _build_agno_tools(task, runtime)

    http_client = httpx.Client(
        timeout=httpx.Timeout(60.0, connect=10.0),
        trust_env=False,
    )
    model = OpenAIChat(
        id=model_id,
        api_key=api_key,
        http_client=http_client,
        temperature=0,
        max_tokens=task["limits"]["output_tokens"],
        request_params={"parallel_tool_calls": False},
    )

    agent = Agent(
        model=model,
        tools=tools,
        markdown=False,
    )

    response = agent.run(task["prompt"])

    # Extract text content
    content = response.content if response is not None else ""
    if not isinstance(content, str):
        content = str(content) if content is not None else ""

    score = score_run(task, runtime, content)

    # Extract token usage from Agno metrics
    # Agno collects run-level metrics in response.metrics (SessionMetrics)
    tokens_in = 0
    tokens_out = 0
    model_requests = None
    metrics = getattr(response, "metrics", None)
    if metrics is not None:
        tokens_in = int(getattr(metrics, "input_tokens", 0) or 0)
        tokens_out = int(getattr(metrics, "output_tokens", 0) or 0)
        model_requests = getattr(metrics, "total_tool_call_count", None)

    return {
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "model_requests": model_requests,
        "cost_usd": _cost_usd(model_id, tokens_in, tokens_out),
        "score": score,
        "output": content,
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
    model_id = request.get("model_id", "gpt-4o")

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
            if has_forbidden:
                failure_type = "policy_blocked"
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
                "message_sanitized": _sanitize(type(exc).__name__ + ": " + str(exc)),
            },
            "score": None,
        }

    sys.stdout.write(json.dumps(result) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
