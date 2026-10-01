"""
BenchClaw benchmark — LangChain 1.4.3 subject worker (create_agent + ChatOpenAI).

Runs in: projects/benchclaw/.venvs/langchain-1.4.3
Protocol: reads one JSON run request from stdin; writes one JSON result to stdout.

Modes:
  fake  — deterministic replay of reference_trace; no network, no credentials
  live  — real OpenAI API call via langchain-openai ChatOpenAI; requires OPENAI_API_KEY in env
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
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_API_KEY"] = ""
os.environ["LANGSMITH_API_KEY"] = ""

if _MODE != "live":
    os.environ["OPENAI_API_KEY"] = ""
    os.environ["ANTHROPIC_API_KEY"] = ""

    def _no_connect(self, address):
        raise ConnectionRefusedError(f"worker_langchain: network blocked — {address}")
    _socket.socket.connect = _no_connect

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

from langchain.agents import create_agent  # noqa: E402
from langchain_core.language_models.chat_models import BaseChatModel  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage  # noqa: E402
from langchain_core.outputs import ChatGeneration, ChatResult  # noqa: E402
from langchain_core.tools import StructuredTool  # noqa: E402

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
# Fake chat model (deterministic, no network)
# ---------------------------------------------------------------------------

class FakeChatModel(BaseChatModel):
    """Replay reference_trace tool calls then emit the final answer."""

    _task: dict[str, Any]
    _fake_mode: str

    def __init__(self, task: dict[str, Any], fake_mode: str) -> None:
        super().__init__()
        object.__setattr__(self, "_task", task)
        object.__setattr__(self, "_fake_mode", fake_mode)

    @property
    def _llm_type(self) -> str:
        return "benchclaw-fake"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        task = self._task
        fake_mode = self._fake_mode
        tool_return_count = sum(1 for m in messages if isinstance(m, ToolMessage))
        budget_exhausted = fake_mode == "budget_exhausted"
        more_calls = tool_return_count < len(task["reference_trace"]) or budget_exhausted

        usage = {
            "input_tokens": FAKE_TOKENS_IN_PER_REQUEST,
            "output_tokens": FAKE_TOKENS_OUT_PER_REQUEST,
            "total_tokens": FAKE_TOKENS_IN_PER_REQUEST + FAKE_TOKENS_OUT_PER_REQUEST,
        }
        if more_calls and tool_return_count <= task["limits"]["tool_calls"]:
            t_name, t_args = fake_tool_args(task, fake_mode, tool_return_count)
            ai_msg = AIMessage(
                content="",
                tool_calls=[{
                    "name": t_name,
                    "args": t_args,
                    "id": f"fake_{tool_return_count}",
                    "type": "tool_call",
                }],
                usage_metadata=usage,
            )
        else:
            ai_msg = AIMessage(content=fake_final_output(task, fake_mode), usage_metadata=usage)
        return ChatResult(generations=[ChatGeneration(message=ai_msg)])


# ---------------------------------------------------------------------------
# Dynamic tool builder — explicit JSON schema, runtime-dispatched
# ---------------------------------------------------------------------------

def _build_lc_tools(task: dict[str, Any], runtime: ToolRuntime) -> list:
    """StructuredTools with a dict args_schema so LangChain passes model args through
    unchanged and the shared ToolRuntime does all validation (same contract as the
    Agno and LangGraph arms)."""
    built = []
    for tool_def in task["tools"]:
        name = tool_def["name"]

        def _make(tool_name: str):
            def _fn(**kwargs: Any) -> str:
                return json.dumps(runtime.call(tool_name, kwargs))
            return _fn

        built.append(
            StructuredTool(
                name=name,
                description=tool_def["description"],
                args_schema=tool_def["input_schema"],
                func=_make(name),
            )
        )
    return built


# ---------------------------------------------------------------------------
# Agent runner
# ---------------------------------------------------------------------------

def _run_agent(model, task: dict[str, Any], runtime: ToolRuntime) -> tuple[str, int, int, int]:
    tools = _build_lc_tools(task, runtime)
    agent = create_agent(model=model, tools=tools)
    state = agent.invoke({"messages": [HumanMessage(content=task["prompt"])]})
    messages = state["messages"]

    tokens_in = tokens_out = requests = 0
    for m in messages:
        if isinstance(m, AIMessage):
            requests += 1
            um = getattr(m, "usage_metadata", None) or {}
            tokens_in += int(um.get("input_tokens", 0) or 0)
            tokens_out += int(um.get("output_tokens", 0) or 0)

    final = messages[-1].content if messages else ""
    if not isinstance(final, str):
        final = str(final)
    return final, tokens_in, tokens_out, requests


def run_with_fake_model(task: dict[str, Any], fake_mode: str) -> dict[str, Any]:
    runtime = ToolRuntime(task)
    final, tin, tout, reqs = _run_agent(FakeChatModel(task, fake_mode), task, runtime)
    return {
        "tokens_in": tin,
        "tokens_out": tout,
        "model_requests": reqs,
        "cost_usd": 0.0,
        "score": score_run(task, runtime, final),
        "output": final,
    }


def run_with_live_model(task: dict[str, Any], api_key: str, model_id: str) -> dict[str, Any]:
    import httpx
    from langchain_openai import ChatOpenAI

    runtime = ToolRuntime(task)
    http_client = httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0), trust_env=False)
    model = ChatOpenAI(
        model=model_id,
        api_key=api_key,
        http_client=http_client,
        temperature=0,
        max_tokens=task["limits"]["output_tokens"],
        use_responses_api=False,
        model_kwargs={"parallel_tool_calls": False},
    )
    final, tin, tout, reqs = _run_agent(model, task, runtime)
    return {
        "tokens_in": tin,
        "tokens_out": tout,
        "model_requests": reqs,
        "cost_usd": _cost_usd(model_id, tin, tout),
        "score": score_run(task, runtime, final),
        "output": final,
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


def _metrics(outcome: dict[str, Any] | None, wall: float, score: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "tokens_in": outcome["tokens_in"] if outcome else None,
        "tokens_out": outcome["tokens_out"] if outcome else None,
        "cost_usd": outcome["cost_usd"] if outcome else 0.0,
        "wall_time_s": round(wall, 4),
        "tool_calls": score["tool_calls"] if score else None,
    }


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

        wall = time.monotonic() - wall_start
        score = outcome["score"]
        if not score["completed"]:
            errors = score["errors"]
            failure_type = "policy_blocked" if any("forbidden" in e for e in errors) else "invalid_final_answer"
            result = {
                "status": "failure",
                "completed": False,
                "metrics": _metrics(outcome, wall, score),
                "failure": {
                    "type": failure_type,
                    "stage": "scoring",
                    "message_sanitized": _sanitize(errors[0] if errors else "score failure"),
                },
                "score": score,
            }
        else:
            result = {
                "status": "success",
                "completed": True,
                "metrics": _metrics(outcome, wall, score),
                "failure": None,
                "score": score,
            }

    except ToolContractError as exc:
        result = {
            "status": "failure",
            "completed": False,
            "metrics": _metrics(None, time.monotonic() - wall_start, None),
            "failure": {
                "type": _classify_tool_contract_error(str(exc)),
                "stage": "tool_execution",
                "message_sanitized": _sanitize(str(exc)),
            },
            "score": None,
        }

    except Exception as exc:
        result = {
            "status": "error",
            "completed": False,
            "metrics": _metrics(None, time.monotonic() - wall_start, None),
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
