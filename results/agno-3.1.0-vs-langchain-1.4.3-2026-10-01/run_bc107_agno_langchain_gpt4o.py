"""
BenchClaw bc-107 — Agno 3.1.0 vs LangChain 1.4.3, same-day scored run.

80 runs: 4 tasks × 10 runs × 2 arms. Model: gpt-4o, temperature 0.
Usage: run_bc107_agno_langchain_gpt4o.py warmup | scored
Stops on the first runner error and when cumulative cost exceeds the cap.
Results append to scored-bc107-raw-{date}.jsonl (warmup: warmup-bc107-raw-{date}.jsonl).
"""

import json
import os
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_ADAPTERS_DIR = _ROOT / "adapters"
_VENVS_DIR = _ROOT / ".venvs"
_CREDENTIALS_DIR = Path.home() / ".openclaw" / "credentials"
_SUITE_PATH = _ROOT / "methodology" / "real-pilot-task-suite-v0.1.0.json"
_DATE = date.today().isoformat()
_MODE = sys.argv[1] if len(sys.argv) > 1 else ""
assert _MODE in {"warmup", "scored"}, "usage: warmup | scored"
_OUTPUT = _ROOT / "operations" / (f"warmup-bc107-raw-{_DATE}.jsonl" if _MODE == "warmup" else f"scored-bc107-raw-{_DATE}.jsonl")
_COST_CAP_USD = 0.30
_MODEL_ID = "gpt-4o"
_RUNS_PER_TASK = 10
_BATCH_SIZE = 10

_SUBJECTS = {
    "agno_3_1_0_gpt4o_live": (
        _VENVS_DIR / "agno-3.1.0" / "bin" / "python",
        _ADAPTERS_DIR / "worker_agno.py",
    ),
    "langchain_1_4_3_gpt4o_live": (
        _VENVS_DIR / "langchain-1.4.3" / "bin" / "python",
        _ADAPTERS_DIR / "worker_langchain.py",
    ),
}


def _build_run_list(suite: dict) -> list[dict]:
    task_ids = ["inventory-reorder"] if _MODE == "warmup" else [t["id"] for t in suite["tasks"]]
    runs_per_task = 1 if _MODE == "warmup" else _RUNS_PER_TASK
    subject_keys = list(_SUBJECTS.keys())
    runs = []
    for task_id in task_ids:
        for run_index in range(runs_per_task):
            # Counterbalance subject order across run indices
            order = subject_keys if run_index % 2 == 0 else list(reversed(subject_keys))
            for subj in order:
                runs.append({
                    "subject": subj,
                    "task_id": task_id,
                    "run_index": run_index,
                })
    return runs


def _already_done(task_id: str, subject: str, run_index: int) -> bool:
    if not _OUTPUT.exists():
        return False
    with open(_OUTPUT) as f:
        for line in f:
            try:
                r = json.loads(line)
                if (
                    r.get("task_id") == task_id
                    and r.get("subject") == subject
                    and r.get("run_index") == run_index
                ):
                    return True
            except Exception:
                pass
    return False


def run_one(subject: str, task: dict, run_index: int, openai_credential: str) -> dict:
    python_exe, worker_script = _SUBJECTS[subject]
    env = {
        "PATH": str(python_exe.parent) + ":/usr/bin:/bin",
        "HOME": str(Path.home()),
        # Suppress tracing/telemetry
        "LANGCHAIN_TRACING_V2": "false",
        "LANGSMITH_TRACING": "false",
        "LANGCHAIN_API_KEY": "",
        "LANGSMITH_API_KEY": "",
        "LOGFIRE_SEND_TO_LOGFIRE": "false",
        "LOGFIRE_TOKEN": "",
        "AGNO_TELEMETRY": "false",
        "AGNO_MONITORING": "false",
        "OPENAI_API_KEY": openai_credential,
        "ANTHROPIC_API_KEY": "",
    }
    request = json.dumps({"task": task, "mode": "live", "model_id": _MODEL_ID})
    wall_start = time.monotonic()
    proc = subprocess.run(
        [str(python_exe), str(worker_script)],
        input=request,
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
    )
    wall_time = round(time.monotonic() - wall_start, 3)
    if not proc.stdout.strip():
        raise RuntimeError(
            f"no output (exit={proc.returncode}): {proc.stderr[:300]}"
        )
    result = json.loads(proc.stdout.strip())
    result["subject"] = subject
    result["task_id"] = task["id"]
    result["run_index"] = run_index
    result["model_id"] = _MODEL_ID
    result["wall_time_outer_s"] = wall_time
    return result


def main():
    with open(_SUITE_PATH) as f:
        suite = json.load(f)
    tasks = {t["id"]: t for t in suite["tasks"]}

    cred_path = _CREDENTIALS_DIR / "openai-api-key"
    openai_credential = cred_path.read_text(encoding="utf-8").strip()

    run_list = _build_run_list(suite)
    pending = [
        r for r in run_list
        if not _already_done(r["task_id"], r["subject"], r["run_index"])
    ]

    total = len(run_list)
    done_before = total - len(pending)
    print(f"bc-107 Agno vs LangChain | {total} total runs | {done_before} already done | {len(pending)} pending")
    print(f"Output: {_OUTPUT.name}")

    completed = done_before
    running_cost = 0.0
    if _OUTPUT.exists():
        for line in open(_OUTPUT):
            try:
                running_cost += json.loads(line).get('metrics', {}).get('cost_usd', 0.0) or 0.0
            except Exception:
                pass
    batches = [pending[i:i + _BATCH_SIZE] for i in range(0, len(pending), _BATCH_SIZE)]

    for batch_num, batch in enumerate(batches, 1):
        print(f"\n--- Batch {batch_num}/{len(batches)} ({len(batch)} runs) ---")
        for item in batch:
            task = tasks[item["task_id"]]
            label = f"{item['subject']}  task={item['task_id']}  run={item['run_index']}"
            try:
                result = run_one(item["subject"], task, item["run_index"], openai_credential)
                metrics = result.get("metrics", {})
                score = result.get("score", {})
                status_char = "✓" if result.get("completed") else "✗"
                print(
                    f"  {status_char} {label} | "
                    f"tok={metrics.get('tokens_in')}/{metrics.get('tokens_out')} "
                    f"cost=${metrics.get('cost_usd', 0):.6f} "
                    f"t={result.get('wall_time_outer_s')}s"
                )
                if score and score.get("errors"):
                    print(f"    errors: {score['errors']}")
                with open(_OUTPUT, "a") as f:
                    f.write(json.dumps(result) + "\n")
                completed += 1
                if result.get("status") == "error":
                    print("STOP: adapter-level error; not retrying.")
                    sys.exit(2)
                running_cost += metrics.get("cost_usd", 0.0) or 0.0
                if running_cost > _COST_CAP_USD:
                    print(f"STOP: cost cap exceeded (${running_cost:.4f}).")
                    sys.exit(3)
            except Exception as exc:
                print(f"  ERROR {label}: {exc}")
                error_record = {
                    "status": "error",
                    "completed": False,
                    "subject": item["subject"],
                    "task_id": item["task_id"],
                    "run_index": item["run_index"],
                    "model_id": _MODEL_ID,
                    "failure": {
                        "type": "runner_error",
                        "message_sanitized": type(exc).__name__,
                    },
                    "metrics": {"tokens_in": None, "tokens_out": None, "cost_usd": 0.0},
                }
                with open(_OUTPUT, "a") as f:
                    f.write(json.dumps(error_record) + "\n")
                print("STOP: runner error; not retrying.")
                sys.exit(2)

    # Final cost summary
    total_cost = 0.0
    successes = 0
    if _OUTPUT.exists():
        with open(_OUTPUT) as f:
            for line in f:
                try:
                    r = json.loads(line)
                    total_cost += r.get("metrics", {}).get("cost_usd", 0.0) or 0.0
                    if r.get("completed"):
                        successes += 1
                except Exception:
                    pass
    print(f"\nDone. {completed}/{total} runs recorded | {successes} completed | total cost ${total_cost:.6f}")
    print(f"→ {_OUTPUT}")


if __name__ == "__main__":
    main()
