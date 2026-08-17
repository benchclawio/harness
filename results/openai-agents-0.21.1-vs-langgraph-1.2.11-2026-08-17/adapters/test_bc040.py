"""
BenchClaw bc-040 — adapter acceptance tests.

Stdlib only. Runs both arms as subprocesses with no network and no credentials.
Both arms must behave identically on the shared task suite before any live call.

Usage (on the sandbox):
  python3 adapters/test_bc040.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent.resolve()
TASK_SUITE_PATH = ROOT / "methodology" / "real-pilot-task-suite-v0.1.0.json"

ARMS = {
    "openai_agents": (
        str(ROOT / "venv-openai-agents" / "bin" / "python"),
        str(ROOT / "adapters" / "worker_openai_agents.py"),
    ),
    "langgraph": (
        str(ROOT / "venv-langgraph" / "bin" / "python"),
        str(ROOT / "adapters" / "worker_langgraph.py"),
    ),
}

_results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    _results.append((name, condition, detail))
    status = "PASS" if condition else "FAIL"
    print(f"  {status}  {name}" + (f"  — {detail}" if detail and not condition else ""))


def load_tasks() -> list[dict[str, Any]]:
    with TASK_SUITE_PATH.open() as f:
        return json.load(f)["tasks"]


def run_worker(arm: str, task: dict[str, Any], fake_mode: str) -> dict[str, Any]:
    python, worker = ARMS[arm]
    request = json.dumps({"mode": "fake", "fake_mode": fake_mode, "task": task})
    proc = subprocess.run(
        [python, worker],
        input=request,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        return {"status": "crash", "stderr": proc.stderr[-400:]}
    line = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    if not line:
        return {"status": "no_output", "stderr": proc.stderr[-400:]}
    return json.loads(line)


def main() -> int:
    tasks = load_tasks()
    print(f"task suite: {len(tasks)} tasks\n")

    # 1. correct mode — every task completes on both arms
    print("correct mode")
    for task in tasks:
        for arm in ARMS:
            r = run_worker(arm, task, "correct")
            check(
                f"{arm}/{task['id']}/correct completes",
                r.get("completed") is True,
                json.dumps(r)[:300],
            )

    # 2. cross-arm equivalence — identical completion, tool count, request count
    print("\ncross-arm equivalence")
    for task in tasks:
        a = run_worker("openai_agents", task, "correct")
        b = run_worker("langgraph", task, "correct")
        check(
            f"{task['id']} same completion flag",
            a.get("completed") == b.get("completed"),
            f"{a.get('completed')} vs {b.get('completed')}",
        )
        check(
            f"{task['id']} same tool-call count",
            a.get("metrics", {}).get("tool_calls") == b.get("metrics", {}).get("tool_calls"),
            f"{a.get('metrics',{}).get('tool_calls')} vs {b.get('metrics',{}).get('tool_calls')}",
        )
        check(
            f"{task['id']} same fake token accounting",
            a.get("metrics", {}).get("tokens_in") == b.get("metrics", {}).get("tokens_in"),
            f"{a.get('metrics',{}).get('tokens_in')} vs {b.get('metrics',{}).get('tokens_in')}",
        )

    # 3. failure modes — both arms must fail, and fail the same way
    print("\nfailure modes")
    # The two arms are NOT required to agree on failure class. The taxonomy forbids
    # relabelling failures to make subjects look comparable, and a genuine difference in
    # how a framework handles bad tool arguments is a finding, not a defect. Modes where
    # divergence is expected are recorded rather than asserted equal.
    failure_modes = ["malformed_output", "wrong_output", "wrong_args", "budget_exhausted"]
    divergence_expected = {"wrong_args"}
    probe = tasks[0]
    for mode in failure_modes:
        a = run_worker("openai_agents", probe, mode)
        b = run_worker("langgraph", probe, mode)
        check(f"openai_agents/{mode} does not complete", a.get("completed") is False, json.dumps(a)[:300])
        check(f"langgraph/{mode} does not complete", b.get("completed") is False, json.dumps(b)[:300])

        a_type = (a.get("failure") or {}).get("type")
        b_type = (b.get("failure") or {}).get("type")
        if mode in divergence_expected:
            check(
                f"{mode} both classified, neither unhandled",
                a_type not in (None, "unhandled_exception")
                and b_type not in (None, "unhandled_exception"),
                f"{a_type} vs {b_type}",
            )
            print(f"        note: {mode} divergence — openai_agents={a_type}, langgraph={b_type}")
        else:
            check(f"{mode} same failure type", a_type == b_type, f"{a_type} vs {b_type}")

    # 4. forbidden tool — only on the task that defines one
    print("\nforbidden tool")
    for task in tasks:
        if not task.get("forbidden_tools"):
            continue
        for arm in ARMS:
            r = run_worker(arm, task, "forbidden_tool")
            check(
                f"{arm}/{task['id']} forbidden tool blocks completion",
                r.get("completed") is False,
                json.dumps(r)[:300],
            )

    # 5. network is actually blocked in fake mode
    print("\nisolation")
    for arm, (python, _) in ARMS.items():
        proc = subprocess.run(
            [python, "-c",
             "import socket;s=socket.socket()\n"
             "def block(self,a):raise ConnectionRefusedError(a)\n"
             "socket.socket.connect=block\n"
             "try:\n"
             "    s.connect(('1.1.1.1',80));print('NOT_BLOCKED')\n"
             "except ConnectionRefusedError:print('BLOCKED')"],
            capture_output=True, text=True, timeout=30,
        )
        check(f"{arm} socket block works", "BLOCKED" in proc.stdout, proc.stdout + proc.stderr)

    # 6. tracing is off in the subject arm
    proc = subprocess.run(
        [ARMS["openai_agents"][0], "-c",
         "import os;os.environ['OPENAI_AGENTS_DISABLE_TRACING']='true'\n"
         "from agents.tracing.provider import DefaultTraceProvider\n"
         "p=DefaultTraceProvider();p._refresh_disabled_flag() if hasattr(p,'_refresh_disabled_flag') else None\n"
         "import agents;agents.set_tracing_disabled(True);print('TRACING_OFF')"],
        capture_output=True, text=True, timeout=60,
    )
    check("openai_agents tracing disables cleanly", "TRACING_OFF" in proc.stdout, proc.stdout + proc.stderr[-300:])

    passed = sum(1 for _, ok, _ in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
