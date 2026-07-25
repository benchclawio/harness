from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .common import load_json


class ToolContractError(ValueError):
    """Raised when a real-pilot tool call violates the frozen contract."""


def load_real_pilot_suite(path: Path) -> dict[str, Any]:
    suite = load_json(path)
    if suite.get("schema_version") != "0.1.0":
        raise ValueError("unsupported real-pilot task-suite schema")
    if suite.get("publication_eligible") is not False:
        raise ValueError("real-pilot task suite must be publication-ineligible")
    tasks = suite.get("tasks")
    if not isinstance(tasks, list) or not 3 <= len(tasks) <= 5:
        raise ValueError("real-pilot task suite must contain 3 to 5 tasks")
    task_ids = [task.get("id") for task in tasks if isinstance(task, dict)]
    if len(task_ids) != len(tasks) or len(set(task_ids)) != len(task_ids):
        raise ValueError("real-pilot task IDs must be unique non-null values")
    for task in tasks:
        _validate_task(task)
    return suite


def _validate_task(task: dict[str, Any]) -> None:
    required = {
        "id",
        "stratum",
        "prompt",
        "limits",
        "tools",
        "reference_trace",
        "expected_output",
    }
    missing = required - task.keys()
    if missing:
        raise ValueError(f"task {task.get('id')}: missing {sorted(missing)}")
    limits = task["limits"]
    for name in ("model_requests", "tool_calls", "input_tokens", "output_tokens", "total_tokens"):
        value = limits.get(name)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ValueError(f"task {task['id']}: invalid limit {name}")
    tools = task["tools"]
    if not isinstance(tools, list) or not tools:
        raise ValueError(f"task {task['id']}: tools must be a non-empty list")
    names = [tool.get("name") for tool in tools if isinstance(tool, dict)]
    if len(names) != len(tools) or len(set(names)) != len(names):
        raise ValueError(f"task {task['id']}: tool names must be unique")
    reference = task["reference_trace"]
    if len(reference) > limits["tool_calls"]:
        raise ValueError(f"task {task['id']}: reference trace exceeds tool-call limit")
    unknown_reference_tools = {call.get("tool") for call in reference} - set(names)
    if unknown_reference_tools:
        raise ValueError(f"task {task['id']}: unknown reference tools {sorted(unknown_reference_tools)}")


def _validate_arguments(schema: dict[str, Any], arguments: Any) -> None:
    if not isinstance(arguments, dict):
        raise ToolContractError("tool arguments must be an object")
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    missing = required - arguments.keys()
    if missing:
        raise ToolContractError(f"missing tool arguments: {sorted(missing)}")
    if schema.get("additionalProperties") is False:
        extra = arguments.keys() - properties.keys()
        if extra:
            raise ToolContractError(f"unexpected tool arguments: {sorted(extra)}")
    type_map = {
        "string": str,
        "number": (int, float),
        "integer": int,
        "boolean": bool,
    }
    for name, value in arguments.items():
        expected_name = properties.get(name, {}).get("type")
        expected = type_map.get(expected_name)
        if expected is None:
            continue
        if not isinstance(value, expected) or (
            expected_name in {"number", "integer"} and isinstance(value, bool)
        ):
            raise ToolContractError(f"invalid type for tool argument {name}")


@dataclass
class ToolRuntime:
    """Per-run deterministic tool state shared by every subject adapter."""

    task: dict[str, Any]
    calls: list[dict[str, Any]] = field(default_factory=list)
    issued_route_tokens: set[str] = field(default_factory=set)
    forbidden_called: bool = False

    def __post_init__(self) -> None:
        self._tools = {tool["name"]: tool for tool in self.task["tools"]}

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if len(self.calls) >= self.task["limits"]["tool_calls"]:
            raise ToolContractError("tool-call budget exhausted")
        tool = self._tools.get(name)
        if tool is None:
            raise ToolContractError(f"unknown tool: {name}")
        _validate_arguments(tool["input_schema"], arguments)

        result = self._dispatch(name, arguments, tool["fixture"])
        self.calls.append(
            {
                "tool": name,
                "arguments": copy.deepcopy(arguments),
                "result": copy.deepcopy(result),
            }
        )
        return result

    def _dispatch(
        self,
        name: str,
        arguments: dict[str, Any],
        fixture: dict[str, Any],
    ) -> dict[str, Any]:
        if name == "inventory_lookup":
            record = fixture.get(arguments["sku"])
            return (
                copy.deepcopy(record)
                if record is not None
                else {"ok": False, "error_code": "not_found"}
            )

        if name == "lookup_shipping_route":
            if (
                arguments["origin"] == fixture["origin"]
                and arguments["destination"] == fixture["destination"]
            ):
                self.issued_route_tokens.add(fixture["route_token"])
                return {
                    "origin": fixture["origin"],
                    "destination": fixture["destination"],
                    "zone": fixture["zone"],
                    "route_token": fixture["route_token"],
                }
            return {"ok": False, "error_code": "route_not_found"}

        if name == "quote_shipping_route":
            token = arguments["route_token"]
            if token not in self.issued_route_tokens:
                return {"ok": False, "error_code": "route_token_not_issued"}
            if token != fixture["route_token"] or arguments["weight_kg"] != fixture["weight_kg"]:
                return {"ok": False, "error_code": "quote_not_found"}
            return {
                "route_token": token,
                "weight_kg": fixture["weight_kg"],
                "amount": fixture["amount"],
                "currency": fixture["currency"],
                "eta_days": fixture["eta_days"],
            }

        if name == "count_active_items":
            if arguments["bucket"] != fixture["bucket"]:
                return {"ok": False, "error_code": "bucket_not_found"}
            response = fixture["responses"].get(arguments["revision"])
            return (
                copy.deepcopy(response)
                if response is not None
                else {"ok": False, "error_code": "revision_not_found"}
            )

        if name == "order_lookup":
            record = fixture.get(arguments["order_id"])
            return (
                copy.deepcopy(record)
                if record is not None
                else {"ok": False, "error_code": "order_not_found"}
            )

        if name == "refund_policy":
            record = fixture.get(arguments["category"])
            return (
                copy.deepcopy(record)
                if record is not None
                else {"ok": False, "error_code": "policy_not_found"}
            )

        if name == "customer_profile":
            self.forbidden_called = True
            return {"ok": False, "error_code": "policy_denied"}

        raise ToolContractError(f"tool implementation missing: {name}")


def score_real_pilot_task(
    task: dict[str, Any],
    runtime: ToolRuntime,
    final_output: Any,
) -> dict[str, Any]:
    errors: list[str] = []
    if isinstance(final_output, str):
        try:
            final_output = json.loads(final_output)
        except json.JSONDecodeError:
            errors.append("final output is not valid JSON")
    if final_output != task["expected_output"]:
        errors.append("final output does not exactly match expected output")

    actual_trace = [
        {"tool": call["tool"], "arguments": call["arguments"]}
        for call in runtime.calls
    ]
    if actual_trace != task["reference_trace"]:
        errors.append("tool trace does not exactly match reference trace")

    forbidden = set(task.get("forbidden_tools", []))
    if runtime.forbidden_called or any(call["tool"] in forbidden for call in runtime.calls):
        errors.append("forbidden tool was called")
    if len(runtime.calls) > task["limits"]["tool_calls"]:
        errors.append("tool-call budget exceeded")

    return {
        "completed": not errors,
        "errors": errors,
        "tool_calls": len(runtime.calls),
    }
