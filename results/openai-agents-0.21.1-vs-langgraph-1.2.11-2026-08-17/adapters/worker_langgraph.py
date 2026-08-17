"""
BenchClaw real-framework pilot — LangGraph 1.2.9 subject worker.

Runs in: projects/benchclaw/.venvs/langgraph
Protocol: reads one JSON run request from stdin; writes one JSON result to stdout.

Modes:
  fake  — deterministic replay of reference_trace; no network, no credentials
  live  — real OpenAI API call via httpx; requires OPENAI_API_KEY in env
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
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_API_KEY"] = ""
os.environ["LANGSMITH_API_KEY"] = ""

# --- block outbound network in fake mode only --------------------------------
if _MODE != "live":
    def _no_connect(self, address):
        raise ConnectionRefusedError(f"worker_langgraph: network blocked — {address}")
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
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool as lc_tool

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
# Fake chat model (deterministic, no network)
# ---------------------------------------------------------------------------

class FakeChatModel(BaseChatModel):
    """Replay reference_trace tool calls then emit the final answer."""

    _task: dict[str, Any]
    _fake_mode: str
    _request_count: int
    _tokens_in: int
    _tokens_out: int

    def __init__(self, task: dict[str, Any], fake_mode: str) -> None:
        super().__init__()
        object.__setattr__(self, "_task", task)
        object.__setattr__(self, "_fake_mode", fake_mode)
        object.__setattr__(self, "_request_count", 0)
        object.__setattr__(self, "_tokens_in", 0)
        object.__setattr__(self, "_tokens_out", 0)

    @property
    def _llm_type(self) -> str:
        return "benchclaw-fake"

    def bind_tools(self, tools, **kwargs):
        return self  # tools registered separately via ToolNode

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        object.__setattr__(self, "_request_count", self._request_count + 1)
        object.__setattr__(self, "_tokens_in", self._tokens_in + FAKE_TOKENS_IN_PER_REQUEST)
        object.__setattr__(self, "_tokens_out", self._tokens_out + FAKE_TOKENS_OUT_PER_REQUEST)

        task = self._task
        fake_mode = self._fake_mode
        reference_trace = task["reference_trace"]
        tool_return_count = sum(1 for m in messages if isinstance(m, ToolMessage))

        budget_exhausted = fake_mode == "budget_exhausted"
        more_calls = tool_return_count < len(reference_trace) or budget_exhausted

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
            )
        else:
            ai_msg = AIMessage(content=fake_final_output(task, fake_mode))

        return ChatResult(generations=[ChatGeneration(message=ai_msg)])


# ---------------------------------------------------------------------------
# Live chat model — minimal httpx-based OpenAI Chat Completions client
# ---------------------------------------------------------------------------

class OpenAIHttpxChatModel(BaseChatModel):
    """Thin httpx wrapper around OpenAI /v1/chat/completions for BenchClaw."""

    _api_key: str
    _model_id: str
    _task: dict[str, Any]
    _request_count: int
    _tokens_in: int
    _tokens_out: int

    def __init__(self, api_key: str, model_id: str, task: dict[str, Any]) -> None:
        super().__init__()
        object.__setattr__(self, "_api_key", api_key)
        object.__setattr__(self, "_model_id", model_id)
        object.__setattr__(self, "_task", task)
        object.__setattr__(self, "_request_count", 0)
        object.__setattr__(self, "_tokens_in", 0)
        object.__setattr__(self, "_tokens_out", 0)

    @property
    def _llm_type(self) -> str:
        return "openai-httpx"

    def bind_tools(self, tools, **kwargs):
        return self  # tool schemas built from task definition directly

    def _oai_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t["input_schema"],
                },
            }
            for t in self._task["tools"]
        ]

    @staticmethod
    def _to_oai_messages(messages) -> list[dict[str, Any]]:
        result = []
        for m in messages:
            if isinstance(m, HumanMessage):
                result.append({"role": "user", "content": m.content})
            elif isinstance(m, AIMessage):
                msg: dict[str, Any] = {"role": "assistant", "content": m.content or ""}
                if m.tool_calls:
                    msg["tool_calls"] = [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["args"]),
                            },
                        }
                        for tc in m.tool_calls
                    ]
                result.append(msg)
            elif isinstance(m, ToolMessage):
                result.append({
                    "role": "tool",
                    "tool_call_id": m.tool_call_id,
                    "content": str(m.content),
                })
        return result

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        import httpx

        object.__setattr__(self, "_request_count", self._request_count + 1)

        body: dict[str, Any] = {
            "model": self._model_id,
            "messages": self._to_oai_messages(messages),
            "temperature": 0,
            "parallel_tool_calls": False,
            "max_tokens": self._task["limits"]["output_tokens"],
        }
        oai_tools = self._oai_tools()
        if oai_tools:
            body["tools"] = oai_tools
            body["tool_choice"] = "auto"

        resp = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            json=body,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()

        usage = data.get("usage", {})
        tokens_in = usage.get("prompt_tokens", 0)
        tokens_out = usage.get("completion_tokens", 0)
        object.__setattr__(self, "_tokens_in", self._tokens_in + tokens_in)
        object.__setattr__(self, "_tokens_out", self._tokens_out + tokens_out)

        oai_msg = data["choices"][0]["message"]
        if oai_msg.get("tool_calls"):
            tool_calls = [
                {
                    "name": tc["function"]["name"],
                    "args": json.loads(tc["function"]["arguments"]),
                    "id": tc["id"],
                    "type": "tool_call",
                }
                for tc in oai_msg["tool_calls"]
            ]
            ai_msg = AIMessage(content="", tool_calls=tool_calls)
        else:
            ai_msg = AIMessage(content=oai_msg.get("content") or "")

        return ChatResult(generations=[ChatGeneration(message=ai_msg)])


# ---------------------------------------------------------------------------
# Dynamic tool builder
# ---------------------------------------------------------------------------

def _build_lc_tools(task: dict[str, Any], runtime: ToolRuntime) -> list:
    """Create langchain @tool callables from the task definition."""
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
        built.append(lc_tool(fn))
    return built


# ---------------------------------------------------------------------------
# Agent runners
# ---------------------------------------------------------------------------

def _run_graph(model, task: dict[str, Any], runtime: ToolRuntime) -> str:
    tools = _build_lc_tools(task, runtime)

    def model_node(state: MessagesState) -> dict:
        response = model.invoke(state["messages"])
        return {"messages": [response]}

    def should_continue(state: MessagesState) -> str:
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return "tools"
        return END

    g = StateGraph(MessagesState)
    g.add_node("model", model_node)
    g.add_node("tools", ToolNode(tools))
    g.add_edge(START, "model")
    g.add_conditional_edges("model", should_continue)
    g.add_edge("tools", "model")
    app = g.compile()

    final_state = app.invoke({"messages": [HumanMessage(content=task["prompt"])]})
    return final_state["messages"][-1].content


def run_with_fake_model(task: dict[str, Any], fake_mode: str) -> dict[str, Any]:
    runtime = ToolRuntime(task)
    model = FakeChatModel(task, fake_mode)
    final_content = _run_graph(model, task, runtime)
    score = score_run(task, runtime, final_content)
    return {
        "model_requests": model._request_count,
        "tokens_in": model._tokens_in,
        "tokens_out": model._tokens_out,
        "cost_usd": 0.0,
        "final_content": final_content,
        "score": score,
    }


def run_with_live_model(task: dict[str, Any], api_key: str, model_id: str) -> dict[str, Any]:
    runtime = ToolRuntime(task)
    model = OpenAIHttpxChatModel(api_key, model_id, task)
    final_content = _run_graph(model, task, runtime)
    score = score_run(task, runtime, final_content)
    return {
        "model_requests": model._request_count,
        "tokens_in": model._tokens_in,
        "tokens_out": model._tokens_out,
        "cost_usd": _cost_usd(model_id, model._tokens_in, model._tokens_out),
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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    request = json.loads(_RAW_REQUEST)
    task = request["task"]
    mode = request.get("mode", "fake")
    fake_mode = request.get("fake_mode", "correct")
    model_id = request.get("model_id", "gpt-4o-mini")
    model_cfg = request.get("model", {
        "provider": "openai" if mode == "live" else "fake",
        "id": model_id if mode == "live" else "benchclaw-fake-1.0",
        "temperature": 0,
    })

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
