"""Framework-neutral agent loop for bc-030, How to Create an AI Agent."""

from __future__ import annotations

import json
import platform
from dataclasses import dataclass
from typing import Any, Protocol


class Model(Protocol):
    def next_action(self, messages: list[dict[str, Any]]) -> dict[str, Any]: ...


@dataclass(frozen=True)
class AgentResult:
    answer: str
    steps: int
    tool_calls: int
    trace: tuple[str, ...]


ORDERS = {
    "A100": {"status": "shipped", "eta": "2026-08-05"},
}


def lookup_order(order_id: str) -> dict[str, str]:
    if order_id not in ORDERS:
        return {"status": "not_found"}
    return ORDERS[order_id]


TOOLS = {"lookup_order": lookup_order}


def run_agent(question: str, model: Model, max_steps: int = 4) -> AgentResult:
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "Answer order-status questions. Use only allowlisted tools. "
                "Never invent an order status."
            ),
        },
        {"role": "user", "content": question},
    ]
    trace: list[str] = []
    tool_calls = 0

    for step in range(1, max_steps + 1):
        action = model.next_action(messages)
        action_type = action.get("type")

        if action_type == "final":
            answer = action.get("answer")
            if not isinstance(answer, str) or not answer.strip():
                raise ValueError("Model returned an invalid final answer")
            trace.append("final")
            return AgentResult(answer, step, tool_calls, tuple(trace))

        if action_type != "tool":
            raise ValueError(f"Unknown action type: {action_type!r}")

        name = action.get("name")
        if name not in TOOLS:
            raise ValueError(f"Blocked tool: {name}")

        arguments = action.get("arguments")
        if set(arguments or {}) != {"order_id"} or not isinstance(arguments["order_id"], str):
            raise ValueError("Invalid lookup_order arguments")

        observation = TOOLS[name](**arguments)
        tool_calls += 1
        trace.append(f"tool:{name}")
        messages.append({"role": "assistant", "content": action})
        messages.append({"role": "tool", "name": name, "content": observation})

    raise RuntimeError(f"Stopped after {max_steps} steps without a final answer")


class ScriptedModel:
    """A deterministic model boundary used to test the orchestration."""

    def next_action(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        tool_messages = [message for message in messages if message["role"] == "tool"]
        if not tool_messages:
            return {"type": "tool", "name": "lookup_order", "arguments": {"order_id": "A100"}}
        order = tool_messages[-1]["content"]
        return {
            "type": "final",
            "answer": f"Order A100 is {order['status']}; ETA {order['eta']}.",
        }


class UnknownToolModel:
    def next_action(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        return {"type": "tool", "name": "delete_order", "arguments": {"order_id": "A100"}}


class EndlessModel:
    def next_action(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        return {"type": "tool", "name": "lookup_order", "arguments": {"order_id": "A100"}}


def captured_error(model: Model, max_steps: int = 4) -> str:
    try:
        run_agent("Where is order A100?", model, max_steps=max_steps)
    except (RuntimeError, ValueError) as error:
        return str(error)
    raise AssertionError("Expected the safety test to fail closed")


def build_output() -> dict[str, Any]:
    happy = run_agent("Where is order A100?", ScriptedModel())
    return {
        "python": platform.python_version(),
        "happy_path": {
            "answer": happy.answer,
            "steps": happy.steps,
            "tool_calls": happy.tool_calls,
            "trace": happy.trace,
        },
        "unknown_tool": captured_error(UnknownToolModel()),
        "step_limit": captured_error(EndlessModel(), max_steps=3),
    }


if __name__ == "__main__":
    print(json.dumps(build_output(), indent=2))

