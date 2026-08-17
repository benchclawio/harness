"""
BenchClaw bc-040 — live run driver.

Executes the frozen task suite against both arms with real model calls, one worker
subprocess per attempt, appending one JSON line per attempt.

Design notes:
  - one attempt per subprocess, matching the adapter contract's process boundary
  - results are appended and flushed immediately, so an OOM kill loses at most one run
  - --resume skips attempts already present in the output file, which is how the
    July pilot recovered from its OOM without discarding data
  - counterbalanced arm order: even run indexes run the subject first, odd the control,
    so provider-side drift cannot systematically favour one arm

Usage:
  python3 adapters/run_bc040.py --runs 1  --out out/warmup.jsonl   --label warmup
  python3 adapters/run_bc040.py --runs 20 --out out/scored.jsonl   --label scored --resume
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent.resolve()
TASK_SUITE_PATH = ROOT / "methodology" / "real-pilot-task-suite-v0.1.0.json"
KEY_PATH = ROOT / ".oai-key"

ARMS = {
    "openai_agents_0_21_1": (
        str(ROOT / "venv-openai-agents" / "bin" / "python"),
        str(ROOT / "adapters" / "worker_openai_agents.py"),
    ),
    "langgraph_1_2_11": (
        str(ROOT / "venv-langgraph" / "bin" / "python"),
        str(ROOT / "adapters" / "worker_langgraph.py"),
    ),
}

MODEL_ID = "gpt-4o"
DELAY_BETWEEN_ATTEMPTS_S = 1.0


def load_tasks() -> list[dict[str, Any]]:
    with TASK_SUITE_PATH.open() as f:
        return json.load(f)["tasks"]


def completed_keys(out_path: Path) -> set[tuple[str, str, int]]:
    if not out_path.exists():
        return set()
    keys = set()
    with out_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            keys.add((rec["arm"], rec["task_id"], rec["run_index"]))
    return keys


def run_attempt(arm: str, task: dict[str, Any], api_key: str) -> dict[str, Any]:
    python, worker = ARMS[arm]
    request = json.dumps({"mode": "live", "model_id": MODEL_ID, "task": task})
    started = time.monotonic()
    try:
        proc = subprocess.run(
            [python, worker],
            input=request,
            capture_output=True,
            text=True,
            timeout=180,
            env={"OPENAI_API_KEY": api_key, "PATH": "/usr/bin:/bin"},
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "failure", "completed": False,
            "metrics": {"tokens_in": None, "tokens_out": None, "cost_usd": 0.0,
                        "wall_time_s": round(time.monotonic() - started, 4),
                        "tool_calls": None},
            "failure": {"type": "timeout", "stage": "harness",
                        "message_sanitized": "attempt exceeded 180s"},
            "score": None,
        }

    if proc.returncode != 0 or not proc.stdout.strip():
        return {
            "status": "error", "completed": False,
            "metrics": {"tokens_in": None, "tokens_out": None, "cost_usd": 0.0,
                        "wall_time_s": round(time.monotonic() - started, 4),
                        "tool_calls": None},
            "failure": {"type": "environment_error", "stage": "harness",
                        "message_sanitized": (proc.stderr or "")[-200:]},
            "score": None,
        }

    return json.loads(proc.stdout.strip().splitlines()[-1])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    api_key = KEY_PATH.read_text().strip()
    tasks = load_tasks()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    done = completed_keys(out_path) if args.resume else set()
    if done:
        print(f"resuming: {len(done)} attempts already recorded", flush=True)

    planned = []
    for run_index in range(args.runs):
        # counterbalance arm order by run index
        arm_order = list(ARMS) if run_index % 2 == 0 else list(ARMS)[::-1]
        for task in tasks:
            for arm in arm_order:
                planned.append((arm, task, run_index))

    todo = [p for p in planned if (p[0], p[1]["id"], p[2]) not in done]
    print(f"{args.label}: {len(todo)} attempts to run ({len(planned)} planned)", flush=True)

    total_cost = 0.0
    completed_count = 0
    with out_path.open("a") as out:
        for n, (arm, task, run_index) in enumerate(todo, 1):
            result = run_attempt(arm, task, api_key)
            record = {
                "label": args.label,
                "arm": arm,
                "task_id": task["id"],
                "run_index": run_index,
                "model_id": MODEL_ID,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "status": result.get("status"),
                "completed": result.get("completed"),
                "metrics": result.get("metrics"),
                "failure": result.get("failure"),
                "score": result.get("score"),
            }
            out.write(json.dumps(record) + "\n")
            out.flush()

            cost = (result.get("metrics") or {}).get("cost_usd") or 0.0
            total_cost += cost
            if result.get("completed"):
                completed_count += 1

            print(
                f"  [{n}/{len(todo)}] {arm:22} {task['id']:28} "
                f"{'OK ' if result.get('completed') else 'FAIL'} "
                f"{(result.get('metrics') or {}).get('wall_time_s')}s "
                f"${cost:.6f}",
                flush=True,
            )
            time.sleep(DELAY_BETWEEN_ATTEMPTS_S)

    print(f"\n{args.label} finished: {completed_count}/{len(todo)} completed, "
          f"${total_cost:.6f} this session", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
