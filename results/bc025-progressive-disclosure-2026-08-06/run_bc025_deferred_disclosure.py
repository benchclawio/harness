#!/usr/bin/env python3
"""Collect the bc-025 progressive-disclosure benchmark.

    python3 operations/run_bc025_deferred_disclosure.py warmup
    python3 operations/run_bc025_deferred_disclosure.py scored

Sequential, no retries, stops on the first failed run, timeout, malformed worker response
or spend-guard violation. The host OOM-killed a parallel run on 2026-07-24; nothing here
runs concurrently.

Cells are interleaved rather than run block by block. Provider-side latency and pricing
drift over minutes, and a design that ran all of arm A before all of arm B would let that
drift masquerade as the effect being measured.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(os.environ.get("BENCHCLAW_ROOT", Path(__file__).resolve().parents[1]))
"""Repository root. Override with BENCHCLAW_ROOT when running from a copy."""
PYTHON = ROOT / ".venvs/pydantic-ai-2.24.0/bin/python"
WORKER = ROOT / "adapters/worker_bc025.py"
SUITE = ROOT / "methodology/bc025-task-suite-v0.1.0.json"
CREDENTIAL = Path.home() / ".openclaw/credentials/openai-api-key"
MODEL_ID = "gpt-4o"
SUBJECT = "pydantic-ai-slim[openai]==2.24.0"

CELLS = [
    {"id": "A-chat", "arm": "always_on", "path": "chat"},
    {"id": "B-chat", "arm": "deferred", "path": "chat"},
    {"id": "A-resp", "arm": "always_on", "path": "responses"},
    {"id": "B-resp", "arm": "deferred", "path": "responses"},
]

STAGES = {
    # repeats, task_count, spend ceiling, per-call reserve.
    # The warmup exercises one task across all four cells: its job is to prove both
    # transport paths and both arms work before the scored batch, not to sample the suite.
    "warmup": (1, 1, 0.10, 0.03),
    "scored": (5, 4, 1.00, 0.03),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_run_order(tasks: list[dict], repeats: int) -> list[dict]:
    """Interleave cells and tasks, alternating direction on each pass."""
    order: list[dict] = []
    for repeat in range(repeats):
        round_tasks = tasks if repeat % 2 == 0 else list(reversed(tasks))
        for task_index, task in enumerate(round_tasks):
            round_cells = CELLS if (repeat + task_index) % 2 == 0 else list(reversed(CELLS))
            for cell in round_cells:
                order.append({"repeat": repeat, "task": task, "cell": cell})
    return order


def run_one(task: dict, cell: dict, capabilities: list, limits: dict, credential: str) -> dict:
    request = json.dumps(
        {
            "task": task,
            "capabilities": capabilities,
            "limits": limits,
            "arm": cell["arm"],
            "path": cell["path"],
            "model_id": MODEL_ID,
            "mode": "live",
        }
    )
    env = {
        "PATH": f"{PYTHON.parent}:/usr/bin:/bin",
        "HOME": str(Path.home()),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "OTEL_SDK_DISABLED": "true",
        "LOGFIRE_SEND_TO_LOGFIRE": "false",
        "LOGFIRE_TOKEN": "",
        "OPENAI_API_KEY": credential,
        "ANTHROPIC_API_KEY": "",
        "HTTP_PROXY": "",
        "HTTPS_PROXY": "",
        "ALL_PROXY": "",
        "NO_PROXY": "*",
    }
    completed = subprocess.run(
        [str(PYTHON), "-I", "-B", str(WORKER)],
        input=request,
        text=True,
        capture_output=True,
        timeout=240,
        env=env,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        raise RuntimeError(
            f"worker failure: exit={completed.returncode}, "
            f"stderr_type={'present' if completed.stderr else 'empty'}"
        )
    return json.loads(completed.stdout)


def main() -> None:
    stage = sys.argv[1] if len(sys.argv) > 1 else ""
    if stage not in STAGES:
        raise SystemExit("Usage: run_bc025_deferred_disclosure.py <warmup|scored>")
    repeats, task_count, ceiling, reserve = STAGES[stage]

    today = datetime.now(UTC).strftime("%Y-%m-%d")
    output = ROOT / f"operations/bc025-{stage}-raw-{today}.jsonl"
    manifest = ROOT / f"operations/bc025-{stage}-manifest-{today}.json"
    if output.exists() or manifest.exists():
        raise SystemExit(f"Refusing to overwrite existing {stage} output")

    credential = CREDENTIAL.read_text(encoding="utf-8").strip()
    if not credential:
        raise SystemExit("OpenAI credential is missing or empty")

    suite = json.loads(SUITE.read_text(encoding="utf-8"))
    capabilities = suite["capabilities"]
    limits = suite["limits"]
    run_order = build_run_order(suite["tasks"][:task_count], repeats)

    spent = 0.0
    started = datetime.now(UTC).isoformat()
    completed_count = 0

    try:
        for sequence, item in enumerate(run_order, start=1):
            if spent + reserve > ceiling:
                raise RuntimeError("spend guard blocked the next call")

            cell, task = item["cell"], item["task"]
            wall_start = time.monotonic()
            result = run_one(task, cell, capabilities, limits, credential)
            outer_wall = round(time.monotonic() - wall_start, 4)

            cost = result.get("metrics", {}).get("cost_usd")
            if not isinstance(cost, (int, float)) or cost < 0:
                raise RuntimeError("worker returned invalid cost")
            spent = round(spent + float(cost), 8)

            record = {
                "sequence": sequence,
                "repeat": item["repeat"],
                "date_utc": datetime.now(UTC).isoformat(),
                "subject": SUBJECT,
                "model_id": MODEL_ID,
                "temperature": 0,
                "parallel_tool_calls": False,
                "provider_retries": 0,
                "task_suite": suite["suite_version"],
                "capability_count": suite["capability_count"],
                "cell": cell["id"],
                "arm": cell["arm"],
                "path": cell["path"],
                "task_id": task["id"],
                "outer_wall_time_s": outer_wall,
                **result,
            }
            with output.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            completed_count += 1

            if result.get("status") != "success" or not result.get("completed"):
                raise RuntimeError(f"run did not complete: {result.get('error_type')}")
            if spent > ceiling:
                raise RuntimeError("recorded spend exceeded the approved ceiling")

    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "stopped",
                    "stage": stage,
                    "completed_runs": completed_count,
                    "planned_runs": len(run_order),
                    "spent_usd": spent,
                    "reason_type": type(exc).__name__,
                    "reason": str(exc)[:200],
                    "output": str(output),
                }
            )
        )
        raise

    payload = {
        "started_utc": started,
        "completed_utc": datetime.now(UTC).isoformat(),
        "status": "complete",
        "stage": stage,
        "subject": SUBJECT,
        "model_id": MODEL_ID,
        "temperature": 0,
        "parallel_tool_calls": False,
        "framework_retries": 0,
        "provider_retries": 0,
        "task_suite": suite["suite_version"],
        "task_suite_sha256": sha256(SUITE),
        "worker_sha256": sha256(WORKER),
        "capability_count": suite["capability_count"],
        "cells": [c["id"] for c in CELLS],
        "runs_per_task_per_cell": repeats,
        "total_runs": completed_count,
        "spend_ceiling_usd": ceiling,
        "actual_cost_usd": spent,
        "raw_jsonl": str(output),
        "raw_jsonl_sha256": sha256(output),
    }
    manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "complete",
                "stage": stage,
                "total_runs": completed_count,
                "actual_cost_usd": spent,
                "output": str(output),
                "manifest": str(manifest),
            }
        )
    )


if __name__ == "__main__":
    main()
