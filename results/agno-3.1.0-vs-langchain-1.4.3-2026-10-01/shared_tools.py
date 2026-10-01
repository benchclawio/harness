"""
BenchClaw real-framework pilot — shared tool machinery.

Stdlib only. Safe to import in both framework venvs and in the harness.
Copied and adapted from harness/src/benchclaw_harness/real_pilot.py.
"""

from __future__ import annotations

import copy
import json
from typing import Any


class ToolContractError(ValueError):
    """Raised when a tool call violates the frozen contract."""


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
        expected_type_name = properties.get(name, {}).get("type")
        expected = type_map.get(expected_type_name)
        if expected is None:
            continue
        if not isinstance(value, expected) or (
            expected_type_name in {"number", "integer"} and isinstance(value, bool)
        ):
            raise ToolContractError(f"invalid type for tool argument {name}")


class ToolRuntime:
    """Per-run deterministic tool state shared by every subject adapter."""

    def __init__(self, task: dict[str, Any]) -> None:
        self.task = task
        self.calls: list[dict[str, Any]] = []
        self.issued_route_tokens: set[str] = set()
        self.forbidden_called: bool = False
        self._tools = {tool["name"]: tool for tool in task["tools"]}

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


def _strip_markdown_fences(text: str) -> str:
    """Remove leading/trailing markdown code fences if present."""
    stripped = text.strip()
    if stripped.startswith("```"):
        first_nl = stripped.find("\n")
        if first_nl != -1:
            stripped = stripped[first_nl + 1:]
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[:-3].rstrip()
    return stripped.strip()


def score_run(
    task: dict[str, Any],
    runtime: ToolRuntime,
    final_output: Any,
) -> dict[str, Any]:
    """Return {completed, errors, tool_calls} for one run attempt."""
    errors: list[str] = []

    if isinstance(final_output, str):
        final_output = _strip_markdown_fences(final_output)
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


# ---------------------------------------------------------------------------
# Fake model configuration helpers
# ---------------------------------------------------------------------------

FAKE_TOKENS_IN_PER_REQUEST = 50
FAKE_TOKENS_OUT_PER_REQUEST = 15


def fake_tool_args(task: dict[str, Any], fake_mode: str, call_index: int) -> tuple[str, dict[str, Any]]:
    """Return (tool_name, arguments) for the call_index-th fake model tool call.

    fake_mode controls which scenario is simulated:
      correct          — follows reference_trace exactly
      budget_exhausted — repeats the last trace entry beyond the limit
      wrong_args       — corrupts argument types on first call
      forbidden_tool   — calls a forbidden tool on first call (task must have one)
    """
    reference_trace = task["reference_trace"]
    trace_len = len(reference_trace)

    if fake_mode == "budget_exhausted":
        idx = min(call_index, trace_len - 1)
        tc = reference_trace[idx]
        return tc["tool"], tc["arguments"]

    if fake_mode == "wrong_args" and call_index == 0:
        tc = reference_trace[0]
        bad_args = {k: 99999 for k in tc["arguments"]}
        return tc["tool"], bad_args

    if fake_mode == "forbidden_tool" and call_index == 0:
        forbidden = task.get("forbidden_tools", [])
        if forbidden:
            first = forbidden[0]
            tool_def = next(t for t in task["tools"] if t["name"] == first)
            dummy_args = {
                k: "test-value" if v.get("type") == "string" else 0
                for k, v in tool_def["input_schema"].get("properties", {}).items()
            }
            return first, dummy_args

    # default: correct
    idx = min(call_index, trace_len - 1)
    tc = reference_trace[idx]
    return tc["tool"], tc["arguments"]


def fake_final_output(task: dict[str, Any], fake_mode: str) -> str:
    """Return the fake model's final text for the given mode."""
    if fake_mode == "malformed_output":
        return "this is not valid json {"
    if fake_mode == "wrong_output":
        return json.dumps({"wrong": "values", "that": "do not match"})
    return json.dumps(task["expected_output"])
