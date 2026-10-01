"""bc-107 adapter acceptance tests: Agno 3.1.0 and LangChain 1.4.3, fake mode, no network."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ADAPTERS = Path(__file__).parent.resolve()
ROOT = ADAPTERS.parent
TASKS = {t["id"]: t for t in json.load(open(ROOT / "methodology" / "real-pilot-task-suite-v0.1.0.json"))["tasks"]}
ARMS = {
    "agno-3.1.0": (str(ROOT / ".venvs/agno-3.1.0/bin/python"), str(ADAPTERS / "worker_agno.py")),
    "langchain-1.4.3": (str(ROOT / ".venvs/langchain-1.4.3/bin/python"), str(ADAPTERS / "worker_langchain.py")),
}
ENV = {"LANGCHAIN_TRACING_V2": "false", "LANGSMITH_TRACING": "false", "AGNO_TELEMETRY": "false",
       "OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": "", "HOME": str(Path.home())}
results = []


def run(arm, task, fake_mode):
    py, worker = ARMS[arm]
    p = subprocess.run([py, worker], input=json.dumps({"task": task, "mode": "fake", "fake_mode": fake_mode}),
                       capture_output=True, text=True, timeout=60,
                       env={**ENV, "PATH": str(Path(py).parent) + ":/usr/bin:/bin"})
    assert p.stdout.strip(), f"no stdout (exit {p.returncode}): {p.stderr[-400:]}"
    return json.loads(p.stdout.strip().splitlines()[-1])


def check(name, fn):
    try:
        fn()
        results.append((name, True, ""))
        print("  PASS ", name)
    except AssertionError as e:
        results.append((name, False, str(e)))
        print("  FAIL ", name, "-", e)


for arm in ARMS:
    for tid, task in TASKS.items():
        def correct(arm=arm, task=task):
            r = run(arm, task, "correct")
            assert r["status"] == "success" and r["completed"] and r["failure"] is None, r
            assert r["score"]["tool_calls"] == len(task["reference_trace"]), r["score"]
        check(f"{arm} correct/{tid}", correct)

        def budget(arm=arm, task=task):
            r = run(arm, task, "budget_exhausted")
            assert r["completed"] is False and r["failure"]["type"] in {"loop_or_budget_exhausted", "malformed_tool_call"}, r
        check(f"{arm} budget_exhausted/{tid}", budget)

    inv, refund = TASKS["inventory-reorder"], TASKS["refund-policy-minimal-tools"]

    def wrong_args(arm=arm):
        r = run(arm, inv, "wrong_args")
        assert r["completed"] is False and r["failure"], r
    check(f"{arm} wrong_args", wrong_args)

    def malformed(arm=arm):
        r = run(arm, inv, "malformed_output")
        assert r["completed"] is False and r["failure"]["type"] == "invalid_final_answer", r
    check(f"{arm} malformed_output", malformed)

    def wrong_output(arm=arm):
        r = run(arm, inv, "wrong_output")
        assert r["completed"] is False and any("does not exactly match" in e for e in r["score"]["errors"]), r
    check(f"{arm} wrong_output", wrong_output)

    def forbidden(arm=arm):
        r = run(arm, refund, "forbidden_tool")
        assert r["completed"] is False and r["failure"]["type"] == "policy_blocked", r
    check(f"{arm} forbidden_tool", forbidden)

    def keys(arm=arm):
        r = run(arm, inv, "correct")
        assert {"status", "completed", "metrics", "failure"} <= r.keys()
        assert {"tokens_in", "tokens_out", "cost_usd", "wall_time_s", "tool_calls"} <= r["metrics"].keys()
    check(f"{arm} result keys", keys)

passed = sum(ok for _, ok, _ in results)
print(f"[bc107 adapters] {passed}/{len(results)} passed")
sys.exit(0 if passed == len(results) else 1)
