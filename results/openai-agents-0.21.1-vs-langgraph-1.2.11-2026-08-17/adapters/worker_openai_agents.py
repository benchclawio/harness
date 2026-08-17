"""
BenchClaw bc-040 — OpenAI Agents SDK 0.21.1 subject worker.

Runs in: /root/bc040/venv-openai-agents
Protocol: reads one JSON run request from stdin; writes one JSON result to stdout.

Modes:
  fake  — deterministic replay of reference_trace; no network, no credentials
  live  — real OpenAI Chat Completions call; requires OPENAI_API_KEY in env

Isolation controls required by operations/bc040-static-audit-2026-08-17.md:
  - tracing disabled three ways (env, set_tracing_disabled, RunConfig) because the SDK
    otherwise POSTs traces INCLUDING prompt and tool payloads to
    https://api.openai.com/v1/traces/ingest
  - Chat Completions forced; the SDK defaults to the Responses API, and the control arm
    uses Chat Completions. Same endpoint for both arms or the benchmark measures endpoints.
  - agents.extensions.experimental.codex and agents.sandbox are never imported
"""

from __future__ import annotations

import asyncio
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

# --- telemetry off (must precede `import agents`) -----------------------------
os.environ["OPENAI_AGENTS_DISABLE_TRACING"] = "true"
os.environ["OPENAI_AGENTS_TRACE_INCLUDE_SENSITIVE_DATA"] = "false"

# --- block outbound network in fake mode only --------------------------------
if _MODE != "live":
    def _no_connect(self, address):
        raise ConnectionRefusedError(f"worker_openai_agents: network blocked — {address}")
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
from agents import (  # noqa: E402
    Agent,
    ModelSettings,
    RunConfig,
    Runner,
    function_tool,
    set_default_openai_api,
    set_tracing_disabled,
)
from agents.items import ModelResponse  # noqa: E402
from agents.models.interface import Model  # noqa: E402
from agents.usage import Usage  # noqa: E402
from openai.types.responses import (  # noqa: E402
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
)

set_tracing_disabled(True)
set_default_openai_api("chat_completions")

# OpenAI model pricing (USD per token in, per token out) — identical table to the
# LangGraph worker so cost is computed the same way on both arms.
_MODEL_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o-mini":       (0.150 / 1_000_000,  0.600 / 1_000_000),
    "gpt-4o":            (2.500 / 1_000_000, 10.000 / 1_000_000),
    "gpt-4o-2024-08-06": (2.500 / 1_000_000, 10.000 / 1_000_000),
    "gpt-4.1-mini":      (0.400 / 1_000_000,  1.600 / 1_000_000),
}
_DEFAULT_PRICING = (2.500 / 1_000_000, 10.000 / 1_000_000)


def _cost_usd(model_id: str, tokens_in: int, tokens_out: int) -> float:
    price_in, price_out = _MODEL_PRICING.get(model_id, _DEFAULT_PRICING)
    return round(tokens_in * price_in + tokens_out * price_out, 8)


# ---------------------------------------------------------------------------
# Fake model (deterministic, no network)
# ---------------------------------------------------------------------------

class FakeModel(Model):
    """Replay reference_trace tool calls then emit the final answer.

    The SDK's Model interface speaks Responses-format items regardless of which wire
    API a concrete model uses, so the fake returns ResponseFunctionToolCall /
    ResponseOutputMessage items directly.
    """

    def __init__(self, task: dict[str, Any], fake_mode: str) -> None:
        self._task = task
        self._fake_mode = fake_mode
        self.request_count = 0
        self.tokens_in = 0
        self.tokens_out = 0

    async def get_response(
        self,
        system_instructions,
        input,
        model_settings,
        tools,
        output_schema,
        handoffs,
        tracing,
        *,
        previous_response_id=None,
        conversation_id=None,
        prompt=None,
    ) -> ModelResponse:
        self.request_count += 1
        self.tokens_in += FAKE_TOKENS_IN_PER_REQUEST
        self.tokens_out += FAKE_TOKENS_OUT_PER_REQUEST

        task = self._task
        fake_mode = self._fake_mode
        reference_trace = task["reference_trace"]

        # Count tool results already returned to the model.
        tool_return_count = 0
        if isinstance(input, list):
            for item in input:
                itype = item.get("type") if isinstance(item, dict) else getattr(item, "type", None)
                if itype == "function_call_output":
                    tool_return_count += 1

        budget_exhausted = fake_mode == "budget_exhausted"
        more_calls = tool_return_count < len(reference_trace) or budget_exhausted

        if more_calls and tool_return_count <= task["limits"]["tool_calls"]:
            t_name, t_args = fake_tool_args(task, fake_mode, tool_return_count)
            item = ResponseFunctionToolCall(
                type="function_call",
                call_id=f"fake_{tool_return_count}",
                name=t_name,
                arguments=json.dumps(t_args),
            )
        else:
            item = ResponseOutputMessage(
                id=f"fake_msg_{self.request_count}",
                type="message",
                role="assistant",
                status="completed",
                content=[
                    ResponseOutputText(
                        type="output_text",
                        text=fake_final_output(task, fake_mode),
                        annotations=[],
                    )
                ],
            )

        return ModelResponse(
            output=[item],
            usage=Usage(
                requests=1,
                input_tokens=FAKE_TOKENS_IN_PER_REQUEST,
                output_tokens=FAKE_TOKENS_OUT_PER_REQUEST,
                total_tokens=FAKE_TOKENS_IN_PER_REQUEST + FAKE_TOKENS_OUT_PER_REQUEST,
            ),
            response_id=f"fake_resp_{self.request_count}",
        )

    def stream_response(self, *args, **kwargs):
        raise NotImplementedError("streaming is disabled for the BenchClaw pilot")


# ---------------------------------------------------------------------------
# Dynamic tool builder
# ---------------------------------------------------------------------------

def _build_sdk_tools(task: dict[str, Any], runtime: ToolRuntime) -> list:
    """Create SDK function_tool callables from the task definition.

    Same exec-built typed dispatch used by the other two workers, so all three arms
    present identical tool names, docstrings and parameter types to the model.
    """
    built = []
    for tool_def in task["tools"]:
        name = tool_def["name"]
        description = tool_def["description"]
        schema = tool_def["input_schema"]
        props = schema.get("properties", {})

        type_map = {
            "string": "str",
            "number": "float",
            "integer": "int",
            "boolean": "bool",
        }
        param_names = sorted(props.keys())
        param_str = ", ".join(
            f"{p}: {type_map.get(props[p].get('type', 'string'), 'str')}"
            for p in param_names
        )
        args_dict = "{" + ", ".join(f'"{p}": {p}' for p in param_names) + "}"

        code = (
            f"def {name}({param_str}) -> str:\n"
            f"    result = _runtime_call({args_dict})\n"
            f"    return json.dumps(result)\n"
        )
        ns: dict[str, Any] = {
            "json": json,
            "_runtime_call": (lambda n: lambda args: runtime.call(n, args))(name),
        }
        exec(code, ns)
        fn = ns[name]
        fn.__doc__ = description
        built.append(function_tool(fn, failure_error_function=None))
    return built


# ---------------------------------------------------------------------------
# Agent runner
# ---------------------------------------------------------------------------

def _run_agent(model, task: dict[str, Any], runtime: ToolRuntime) -> tuple[str, Any]:
    tools = _build_sdk_tools(task, runtime)

    agent = Agent(
        name="benchclaw-subject",
        instructions=None,
        tools=tools,
        model=model,
        model_settings=ModelSettings(
            temperature=0,
            parallel_tool_calls=False,
            max_tokens=task["limits"]["output_tokens"],
        ),
    )

    # One model turn per tool call plus a final answer turn.
    max_turns = task["limits"]["tool_calls"] + 2

    result = asyncio.run(
        Runner.run(
            agent,
            task["prompt"],
            max_turns=max_turns,
            run_config=RunConfig(
                tracing_disabled=True,
                trace_include_sensitive_data=False,
            ),
        )
    )
    return str(result.final_output), result


def run_with_fake_model(task: dict[str, Any], fake_mode: str) -> dict[str, Any]:
    runtime = ToolRuntime(task)
    model = FakeModel(task, fake_mode)
    final_content, _ = _run_agent(model, task, runtime)
    score = score_run(task, runtime, final_content)
    return {
        "model_requests": model.request_count,
        "tokens_in": model.tokens_in,
        "tokens_out": model.tokens_out,
        "cost_usd": 0.0,
        "final_content": final_content,
        "score": score,
    }


def run_with_live_model(task: dict[str, Any], api_key: str, model_id: str) -> dict[str, Any]:
    from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key, max_retries=0, timeout=60.0)
    model = OpenAIChatCompletionsModel(model=model_id, openai_client=client)

    runtime = ToolRuntime(task)
    final_content, result = _run_agent(model, task, runtime)
    score = score_run(task, runtime, final_content)

    usage = result.context_wrapper.usage
    tokens_in = usage.input_tokens or 0
    tokens_out = usage.output_tokens or 0

    return {
        "model_requests": usage.requests or 0,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": _cost_usd(model_id, tokens_in, tokens_out),
        "final_content": final_content,
        "score": score,
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


def _unwrap_tool_contract_error(exc: BaseException) -> ToolContractError | None:
    """The SDK wraps tool exceptions; walk the cause chain for our contract error."""
    seen = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if isinstance(cur, ToolContractError):
            return cur
        cur = cur.__cause__ or cur.__context__
    return None


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

        metrics = {
            "tokens_in": outcome["tokens_in"],
            "tokens_out": outcome["tokens_out"],
            "cost_usd": outcome["cost_usd"],
            "wall_time_s": round(wall_time, 4),
            "tool_calls": score["tool_calls"],
        }

        if not score["completed"]:
            errors = score["errors"]
            if any("forbidden" in e for e in errors):
                failure_type = "policy_blocked"
            else:
                failure_type = "invalid_final_answer"
            result: dict[str, Any] = {
                "status": "failure",
                "completed": False,
                "metrics": metrics,
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
                "metrics": metrics,
                "failure": None,
                "score": score,
            }

    except json.JSONDecodeError as exc:
        wall_time = time.monotonic() - wall_start
        result = {
            "status": "failure",
            "completed": False,
            "metrics": {
                "tokens_in": None, "tokens_out": None, "cost_usd": 0.0,
                "wall_time_s": round(wall_time, 4), "tool_calls": None,
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
        contract_error = _unwrap_tool_contract_error(exc)
        if contract_error is not None:
            failure = {
                "type": _classify_tool_contract_error(str(contract_error)),
                "stage": "tool_execution",
                "message_sanitized": _sanitize(str(contract_error)),
            }
            status = "failure"
        elif type(exc).__name__ == "MaxTurnsExceeded":
            failure = {
                "type": "loop_or_budget_exhausted",
                "stage": "agent_loop",
                "message_sanitized": _sanitize(type(exc).__name__),
            }
            status = "failure"
        elif type(exc).__name__ == "ModelBehaviorError":
            # The SDK validates tool arguments against the function signature and raises
            # before the tool body runs. Taxonomy: "tool name/arguments cannot be parsed
            # or validated" — malformed_tool_call.
            failure = {
                "type": "malformed_tool_call",
                "stage": "tool_execution",
                "message_sanitized": _sanitize(type(exc).__name__),
            }
            status = "failure"
        else:
            failure = {
                "type": "unhandled_exception",
                "stage": "adapter",
                "message_sanitized": _sanitize(type(exc).__name__),
            }
            status = "error"

        result = {
            "status": status,
            "completed": False,
            "metrics": {
                "tokens_in": None, "tokens_out": None, "cost_usd": 0.0,
                "wall_time_s": round(wall_time, 4), "tool_calls": None,
            },
            "failure": failure,
            "score": None,
        }

    sys.stdout.write(json.dumps(result) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
