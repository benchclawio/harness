#!/usr/bin/env python3
"""bc-039 workload runner: execute the frozen scripted workload under one arm.

The runner is deliberately arm-agnostic. It walks the frozen scenario list, opens a span per
step through whatever `Tracer` it is handed, and returns the exact list of spans it *issued*.
That issued list is the denominator; the exported records read back from a tool's own API are
the numerator. Nothing here reads a vendor dashboard.

Correlation, and why it matters
-------------------------------
Every span carries `benchclaw.run_id` and `benchclaw.step_index` as attributes. The addendum
requires that "any dropped span is a finding and is reported individually", which a bare
count cannot do: 139 of 140 tells you nothing about which one went missing or under what
conditions. With a correlation key the exporter reader names the exact step.

Dependency posture
------------------
This module imports nothing outside the standard library. The OpenTelemetry, Langfuse and
Phoenix wiring lives behind the `Tracer` protocol in `bc039_arms.py` and is imported lazily,
so the counting, nesting and error logic is fully testable on a host with none of those
packages installed. What cannot be tested off the sandbox is the real SDK wiring itself, and
that is exactly what the positive control gate exists to prove before any measured run.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Protocol

ROOT = Path(os.environ.get("BENCHCLAW_ROOT", Path(__file__).resolve().parents[1]))
SUITE_PATH = ROOT / "methodology/bc039-workload-v0.1.0.json"

LLM = "llm"
TOOL = "tool"
RETRIEVAL = "retrieval"


class ToolFailure(RuntimeError):
    """Raised by a step marked `fails`. Injected on purpose; counted as an error record."""


class Span(Protocol):
    def set_attribute(self, key: str, value: Any) -> None: ...
    def record_error(self, exc: BaseException) -> None: ...
    def end(self) -> None: ...


class Tracer(Protocol):
    def start_span(self, name: str, kind: str, parent: Any, attributes: dict) -> Span: ...


# ---------------------------------------------------------------------------
# Deterministic step implementations
# ---------------------------------------------------------------------------

def _run_tool(suite: dict, name: str, detail: dict, fails: bool) -> dict:
    if fails:
        # The injected failure is a real exception through the real code path, not a flag
        # set on a span. An SDK that only records successful calls has to actually miss it.
        raise ToolFailure(f"{name}: no record for {json.dumps(detail, sort_keys=True)}")
    fixture = suite["tool_fixtures"][name]
    key = next(iter(detail.values()))
    if key not in fixture:
        raise ToolFailure(f"{name}: no record for {key}")
    return fixture[key]


def _run_retrieval(suite: dict, detail: dict) -> dict:
    key = detail["key"]
    corpus = suite["corpus"]
    if key not in corpus:
        raise ToolFailure(f"retrieval: no document {key}")
    return {"key": key, "text": corpus[key]}


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_scenario(
    suite: dict,
    scenario: dict,
    tracer: Tracer,
    call_model: Callable[[str, dict], dict],
    run_id: str,
    step_offset: int,
) -> dict:
    """Execute one scenario. Returns the issued-span record for it.

    `call_model(prompt, context)` returns {"text": str, "tokens_in": int, "tokens_out": int}.
    Its return value never influences control flow — see the workload generator's docstring.
    """
    spans: list[Any] = []
    issued: list[dict] = []
    outputs: list[str] = []
    tokens_in = 0
    tokens_out = 0

    for local_index, st in enumerate(scenario["steps"]):
        step_index = step_offset + local_index
        parent = spans[st["parent"]] if st["parent"] is not None else None
        attributes = {
            "benchclaw.run_id": run_id,
            "benchclaw.step_index": step_index,
            "benchclaw.scenario": scenario["id"],
            "benchclaw.kind": st["kind"],
        }
        span = tracer.start_span(st["name"], st["kind"], parent, attributes)
        spans.append(span)

        record = {
            # run_id travels on every issued record: correlation is (run_id, step_index),
            # and the comparison must never be able to alias one run's spans onto another's.
            "run_id": run_id,
            "step_index": step_index,
            "scenario": scenario["id"],
            "kind": st["kind"],
            "name": st["name"],
            "parent_step_index": None if st["parent"] is None else step_offset + st["parent"],
            "expected_error": bool(st["fails"]),
        }
        started = time.monotonic()
        try:
            if st["kind"] == LLM:
                if st["fails"]:
                    raise ToolFailure(f"{st['name']}: injected model failure")
                result = call_model(scenario["prompt"], {"step": st["name"]})
                outputs.append(result["text"])
                tokens_in += int(result.get("tokens_in", 0))
                tokens_out += int(result.get("tokens_out", 0))
                span.set_attribute("benchclaw.tokens_in", int(result.get("tokens_in", 0)))
                span.set_attribute("benchclaw.tokens_out", int(result.get("tokens_out", 0)))
            elif st["kind"] == TOOL:
                _run_tool(suite, st["name"], st["detail"], st["fails"])
            elif st["kind"] == RETRIEVAL:
                _run_retrieval(suite, st["detail"])
            else:
                raise RuntimeError(f"unknown step kind: {st['kind']}")
            record["errored"] = False
        except ToolFailure as exc:
            # An injected failure is expected and recorded; it must not abort the scenario,
            # because the steps after it are part of the denominator too.
            span.record_error(exc)
            record["errored"] = True
            record["error_message"] = str(exc)
            if not st["fails"]:
                raise
        finally:
            record["wall_time_s"] = round(time.monotonic() - started, 6)
            span.end()

        issued.append(record)

    return {
        "scenario": scenario["id"],
        "issued": issued,
        "outputs": outputs,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
    }


def run_workload(
    tracer: Tracer,
    call_model: Callable[[str, dict], dict],
    suite: dict | None = None,
    run_id: str | None = None,
) -> dict:
    """Execute all scenarios once. One call == one 'run' in the addendum's run count."""
    suite = suite or json.loads(SUITE_PATH.read_text())
    run_id = run_id or uuid.uuid4().hex
    started = time.monotonic()

    scenarios = []
    step_offset = 0
    for scenario in suite["scenarios"]:
        result = run_scenario(suite, scenario, tracer, call_model, run_id, step_offset)
        scenarios.append(result)
        step_offset += len(scenario["steps"])

    issued = [record for sc in scenarios for record in sc["issued"]]
    return {
        "run_id": run_id,
        "suite_version": suite["suite_version"],
        "scenarios": scenarios,
        "issued": issued,
        "issued_counts": count_issued(issued),
        "tokens_in": sum(sc["tokens_in"] for sc in scenarios),
        "tokens_out": sum(sc["tokens_out"] for sc in scenarios),
        "wall_time_s": round(time.monotonic() - started, 4),
    }


def count_issued(issued: list[dict]) -> dict:
    counts = {LLM: 0, TOOL: 0, RETRIEVAL: 0, "errors": 0, "spans": 0, "nested_edges": 0}
    for record in issued:
        counts[record["kind"]] += 1
        counts["spans"] += 1
        if record["errored"]:
            counts["errors"] += 1
        if record["parent_step_index"] is not None:
            counts["nested_edges"] += 1
    return counts
