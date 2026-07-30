"""
BenchClaw real-framework pilot — adapter acceptance tests.

Stdlib only. Runs both workers as subprocesses with no network and no credentials.

Usage:
  python adapters/test_adapters.py

All tests must pass before moving to live-model warmups.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# --- paths -------------------------------------------------------------------
ADAPTERS_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = ADAPTERS_DIR.parent
TASK_SUITE_PATH = PROJECT_ROOT / "task-suites" / "pilot-v0.1.1.json"

VENVS = PROJECT_ROOT / ".venvs"
LG_PYTHON = str(VENVS / "langgraph" / "bin" / "python")
PAI_PYTHON = str(VENVS / "pydantic-ai" / "bin" / "python")
LG_WORKER = str(ADAPTERS_DIR / "worker_langgraph.py")
PAI_WORKER = str(ADAPTERS_DIR / "worker_pydantic_ai.py")

# --- test harness ------------------------------------------------------------

_results: list[tuple[str, bool, str]] = []


def test(name: str):
    def decorator(fn):
        start = time.monotonic()
        try:
            fn()
            elapsed = time.monotonic() - start
            _results.append((name, True, f"{elapsed*1000:.0f}ms"))
            print(f"  PASS  {name}  ({elapsed*1000:.0f}ms)")
        except AssertionError as exc:
            elapsed = time.monotonic() - start
            _results.append((name, False, str(exc)))
            print(f"  FAIL  {name}  ({elapsed*1000:.0f}ms)")
            print(f"        {exc}")
        return fn
    return decorator


# --- helpers -----------------------------------------------------------------

def load_task_suite() -> list[dict[str, Any]]:
    with TASK_SUITE_PATH.open() as f:
        suite = json.load(f)
    return suite["tasks"]


def run_worker(python: str, worker: str, task: dict, fake_mode: str, timeout: int = 30) -> dict:
    request = json.dumps({"task": task, "mode": "fake", "fake_mode": fake_mode})
    proc = subprocess.run(
        [python, worker],
        input=request,
        capture_output=True,
        text=True,
        timeout=timeout,
        env={
            "PATH": str(Path(python).parent) + ":/usr/bin:/bin",
            "HOME": str(Path.home()),
            "LANGCHAIN_TRACING_V2": "false",
            "LANGSMITH_TRACING": "false",
            "LANGCHAIN_API_KEY": "",
            "LANGSMITH_API_KEY": "",
            "LOGFIRE_SEND_TO_LOGFIRE": "false",
            "LOGFIRE_TOKEN": "",
            "OPENAI_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
        },
    )
    if proc.stderr.strip():
        # Print stderr for debugging (it goes to test output, not worker output)
        for line in proc.stderr.strip().splitlines():
            if not line.startswith("WARNING") and "UserWarning" not in line:
                print(f"    stderr: {line}", file=sys.stderr)
    if not proc.stdout.strip():
        raise AssertionError(
            f"worker produced no stdout (exit={proc.returncode})\n"
            f"stderr: {proc.stderr[:400]}"
        )
    return json.loads(proc.stdout.strip())


TASKS = load_task_suite()
TASK_BY_ID = {t["id"]: t for t in TASKS}

# =============================================================================
# HAPPY PATH: all 4 tasks × 2 workers
# =============================================================================

print("\n[adapters] happy-path tests (correct fake mode)")

for task in TASKS:
    tid = task["id"]

    @test(f"langgraph  correct/{tid}")
    def _(task=task, tid=tid):
        r = run_worker(LG_PYTHON, LG_WORKER, task, "correct")
        assert r["status"] == "success", f"expected success, got {r['status']}: {r.get('failure')}"
        assert r["completed"] is True
        assert r["failure"] is None
        score = r["score"]
        assert score["completed"] is True, f"score errors: {score['errors']}"
        assert score["tool_calls"] == len(task["reference_trace"]), score

    @test(f"pydantic-ai correct/{tid}")
    def _(task=task, tid=tid):
        r = run_worker(PAI_PYTHON, PAI_WORKER, task, "correct")
        assert r["status"] == "success", f"expected success, got {r['status']}: {r.get('failure')}"
        assert r["completed"] is True
        assert r["failure"] is None
        score = r["score"]
        assert score["completed"] is True, f"score errors: {score['errors']}"
        assert score["tool_calls"] == len(task["reference_trace"]), score


# =============================================================================
# FAILURE MODES
# =============================================================================

print("\n[adapters] failure-mode tests")

# --- budget_exhausted: both workers ---
for task in TASKS[:2]:  # inventory (limit=1) and shipping (limit=2) are good targets
    tid = task["id"]

    @test(f"langgraph  budget_exhausted/{tid}")
    def _(task=task, tid=tid):
        r = run_worker(LG_PYTHON, LG_WORKER, task, "budget_exhausted")
        assert r["completed"] is False
        assert r["status"] in {"failure", "error"}
        f = r.get("failure") or {}
        assert f.get("type") in {"loop_or_budget_exhausted", "malformed_tool_call"}, f
        assert f.get("stage") is not None

    @test(f"pydantic-ai budget_exhausted/{tid}")
    def _(task=task, tid=tid):
        r = run_worker(PAI_PYTHON, PAI_WORKER, task, "budget_exhausted")
        assert r["completed"] is False
        assert r["status"] in {"failure", "error"}
        f = r.get("failure") or {}
        assert f.get("type") in {"loop_or_budget_exhausted", "malformed_tool_call"}, f

# --- wrong_args: first task (inventory, sku must be a string) ---
wrong_args_task = TASK_BY_ID["inventory-reorder"]

@test("langgraph  wrong_args/inventory-reorder")
def _():
    r = run_worker(LG_PYTHON, LG_WORKER, wrong_args_task, "wrong_args")
    assert r["completed"] is False, f"should not complete: {r}"
    assert r["failure"] is not None, "failure must be set"
    # LangGraph coerces int→str via Pydantic; wrong value causes trace mismatch not type error
    assert r["failure"]["type"] in {"malformed_tool_call", "invalid_final_answer"}, r["failure"]

@test("pydantic-ai wrong_args/inventory-reorder")
def _():
    r = run_worker(PAI_PYTHON, PAI_WORKER, wrong_args_task, "wrong_args")
    assert r["completed"] is False, f"should not complete: {r}"
    assert r["failure"] is not None, "failure must be set"
    # Pydantic AI wraps ToolContractError as UnexpectedModelBehavior
    assert r["failure"]["type"] in {"malformed_tool_call", "invalid_final_answer", "unhandled_exception"}, r["failure"]

# --- malformed_output: both workers ---
malformed_task = TASK_BY_ID["inventory-reorder"]

@test("langgraph  malformed_output/inventory-reorder")
def _():
    r = run_worker(LG_PYTHON, LG_WORKER, malformed_task, "malformed_output")
    assert r["completed"] is False
    f = r.get("failure") or {}
    assert f.get("type") == "invalid_final_answer", f

@test("pydantic-ai malformed_output/inventory-reorder")
def _():
    r = run_worker(PAI_PYTHON, PAI_WORKER, malformed_task, "malformed_output")
    assert r["completed"] is False
    f = r.get("failure") or {}
    assert f.get("type") == "invalid_final_answer", f

# --- wrong_output: both workers ---
@test("langgraph  wrong_output/inventory-reorder")
def _():
    r = run_worker(LG_PYTHON, LG_WORKER, malformed_task, "wrong_output")
    assert r["completed"] is False
    score = r.get("score") or {}
    assert not score.get("completed")
    errors = score.get("errors", [])
    assert any("does not exactly match" in e for e in errors), errors

@test("pydantic-ai wrong_output/inventory-reorder")
def _():
    r = run_worker(PAI_PYTHON, PAI_WORKER, malformed_task, "wrong_output")
    assert r["completed"] is False
    score = r.get("score") or {}
    assert not score.get("completed")
    errors = score.get("errors", [])
    assert any("does not exactly match" in e for e in errors), errors

# --- forbidden_tool: refund-policy task has a customer_profile forbidden tool ---
forbidden_task = TASK_BY_ID["refund-policy-minimal-tools"]

@test("langgraph  forbidden_tool/refund-policy-minimal-tools")
def _():
    r = run_worker(LG_PYTHON, LG_WORKER, forbidden_task, "forbidden_tool")
    assert r["completed"] is False
    f = r.get("failure") or {}
    assert f.get("type") == "policy_blocked", f
    score = r.get("score") or {}
    errors = score.get("errors", []) if score else []
    assert any("forbidden" in e for e in errors), errors

@test("pydantic-ai forbidden_tool/refund-policy-minimal-tools")
def _():
    r = run_worker(PAI_PYTHON, PAI_WORKER, forbidden_task, "forbidden_tool")
    assert r["completed"] is False
    f = r.get("failure") or {}
    assert f.get("type") == "policy_blocked", f
    score = r.get("score") or {}
    errors = score.get("errors", []) if score else []
    assert any("forbidden" in e for e in errors), errors


# =============================================================================
# STRUCTURAL INVARIANTS
# =============================================================================

print("\n[adapters] structural invariant tests")

@test("all result dicts have required keys")
def _():
    required = {"status", "completed", "metrics", "failure"}
    metrics_required = {"tokens_in", "tokens_out", "cost_usd", "wall_time_s", "tool_calls"}
    task = TASK_BY_ID["inventory-reorder"]
    for python, worker, label in [
        (LG_PYTHON, LG_WORKER, "langgraph"),
        (PAI_PYTHON, PAI_WORKER, "pydantic-ai"),
    ]:
        r = run_worker(python, worker, task, "correct")
        missing = required - r.keys()
        assert not missing, f"{label}: missing keys {missing}"
        m = r["metrics"]
        assert isinstance(m, dict), f"{label}: metrics is not a dict"
        missing_m = metrics_required - m.keys()
        assert not missing_m, f"{label}: missing metric keys {missing_m}"

@test("success result: cost_usd=0.0, wall_time_s positive, tool_calls matches trace")
def _():
    task = TASK_BY_ID["dependent-shipping-quote"]
    for python, worker, label in [
        (LG_PYTHON, LG_WORKER, "langgraph"),
        (PAI_PYTHON, PAI_WORKER, "pydantic-ai"),
    ]:
        r = run_worker(python, worker, task, "correct")
        m = r["metrics"]
        assert m["cost_usd"] == 0.0, f"{label}: {m['cost_usd']}"
        assert isinstance(m["wall_time_s"], float) and m["wall_time_s"] > 0, f"{label}: {m['wall_time_s']}"
        assert m["tool_calls"] == 2, f"{label}: expected 2 tool_calls, got {m['tool_calls']}"

@test("stale-revision task: both workers make exactly 2 tool calls")
def _():
    task = TASK_BY_ID["recover-stale-revision"]
    for python, worker, label in [
        (LG_PYTHON, LG_WORKER, "langgraph"),
        (PAI_PYTHON, PAI_WORKER, "pydantic-ai"),
    ]:
        r = run_worker(python, worker, task, "correct")
        assert r["completed"] is True, f"{label}: {r}"
        assert r["metrics"]["tool_calls"] == 2, f"{label}: expected 2, got {r['metrics']['tool_calls']}"

@test("both workers produce identical per-task completion for correct mode")
def _():
    for task in TASKS:
        r_lg = run_worker(LG_PYTHON, LG_WORKER, task, "correct")
        r_pai = run_worker(PAI_PYTHON, PAI_WORKER, task, "correct")
        assert r_lg["completed"] == r_pai["completed"], (
            f"task {task['id']}: LG={r_lg['completed']}, PAI={r_pai['completed']}"
        )
        assert r_lg["metrics"]["tool_calls"] == r_pai["metrics"]["tool_calls"], (
            f"task {task['id']}: tool_calls differ: LG={r_lg['metrics']['tool_calls']}, PAI={r_pai['metrics']['tool_calls']}"
        )

@test("failure results have non-null failure dict with required keys")
def _():
    failure_required = {"type", "stage", "message_sanitized"}
    task = TASK_BY_ID["inventory-reorder"]
    for fake_mode in ("budget_exhausted", "wrong_args", "malformed_output"):
        for python, worker, label in [
            (LG_PYTHON, LG_WORKER, "langgraph"),
            (PAI_PYTHON, PAI_WORKER, "pydantic-ai"),
        ]:
            r = run_worker(python, worker, task, fake_mode)
            assert r["completed"] is False, f"{label}/{fake_mode}: should not complete"
            f = r.get("failure")
            assert isinstance(f, dict), f"{label}/{fake_mode}: failure should be a dict, got {f!r}"
            missing = failure_required - f.keys()
            assert not missing, f"{label}/{fake_mode}: failure missing keys {missing}"
            assert len(f.get("message_sanitized", "")) <= 240, f"{label}/{fake_mode}: message too long"


# =============================================================================
# SUMMARY
# =============================================================================

print()
passed = sum(1 for _, ok, _ in _results if ok)
failed = sum(1 for _, ok, _ in _results if not ok)
total = len(_results)
print(f"[adapters] {passed}/{total} passed", end="")
if failed:
    print(f"  ({failed} FAILED)")
    for name, ok, detail in _results:
        if not ok:
            print(f"  FAIL  {name}: {detail}")
    sys.exit(1)
else:
    print()
    sys.exit(0)
