"""
BenchClaw bc-040 — analysis of the scored run.

Reads the raw JSONL from adapters/run_bc040.py and produces the figures the
benchmark protocol requires: completion rate with a Wilson interval, token and
cost spread, latency median/p95, the failure taxonomy, and paired
subject-minus-control differences with bootstrap intervals.

Pairing is by (task_id, run_index): both arms ran the same task at the same run
index within minutes of each other, so the pair controls for provider drift.

Usage:
  python3 operations/bc040_analyze.py \
      operations/bc040-scored-raw-2026-08-17.jsonl \
      operations/bc040-analysis-2026-08-17.json
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(ROOT / "harness" / "src"))

from benchclaw_harness.analysis import (  # noqa: E402
    bootstrap_interval,
    summarize_values,
    wilson_interval,
)

SUBJECT = "openai_agents_0_21_1"
CONTROL = "langgraph_1_2_11"
SEED = 20260817
REPLICATES = 10000
CONFIDENCE = 0.95
METRICS = ["tokens_in", "tokens_out", "cost_usd", "wall_time_s", "tool_calls"]


def load(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def arm_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    completed = sum(1 for r in rows if r["completed"])
    failures = Counter(
        r["failure"]["type"] for r in rows if r.get("failure") is not None
    )
    metrics = {
        m: summarize_values([float(r["metrics"][m]) for r in rows if r["metrics"].get(m) is not None])
        for m in METRICS
    }
    return {
        "attempts": len(rows),
        "completed": completed,
        "completion_rate": completed / len(rows) if rows else None,
        "completion_wilson_95": wilson_interval(completed, len(rows)),
        "failure_counts": dict(sorted(failures.items())),
        "total_cost_usd": round(sum(r["metrics"]["cost_usd"] for r in rows), 6),
        "metrics": metrics,
    }


def paired(rows: list[dict[str, Any]], metric: str, task_id: str | None = None) -> list[tuple[float, float]]:
    index: dict[tuple[str, int], dict[str, float]] = defaultdict(dict)
    for r in rows:
        if task_id is not None and r["task_id"] != task_id:
            continue
        value = r["metrics"].get(metric)
        if value is None:
            continue
        index[(r["task_id"], r["run_index"])][r["arm"]] = float(value)
    return [
        (v[SUBJECT], v[CONTROL])
        for v in index.values()
        if SUBJECT in v and CONTROL in v
    ]


def difference(rows: list[dict[str, Any]], metric: str, task_id: str | None = None) -> dict[str, Any]:
    pairs = paired(rows, metric, task_id)
    if not pairs:
        return {"pairs": 0}
    deltas = [a - b for a, b in pairs]
    interval = bootstrap_interval(pairs, statistics.median, SEED, REPLICATES, CONFIDENCE)
    crosses_zero = interval is not None and interval[0] <= 0 <= interval[1]
    return {
        "pairs": len(pairs),
        "subject_median": statistics.median(a for a, _ in pairs),
        "control_median": statistics.median(b for _, b in pairs),
        "median_delta": statistics.median(deltas),
        "bootstrap_95": interval,
        "crosses_zero": crosses_zero,
        "interpretation": "no measurable difference" if crosses_zero else "difference outside the interval",
    }


def main() -> int:
    raw_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2])
    rows = load(raw_path)

    by_arm: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_arm_task: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_arm[r["arm"]].append(r)
        by_arm_task[(r["arm"], r["task_id"])].append(r)

    tasks = sorted({r["task_id"] for r in rows})

    report: dict[str, Any] = {
        "benchmark": "bc-040",
        "date_utc": "2026-08-17",
        "model_id": rows[0]["model_id"],
        "subject": SUBJECT,
        "control": CONTROL,
        "total_attempts": len(rows),
        "total_cost_usd": round(sum(r["metrics"]["cost_usd"] for r in rows), 6),
        "runs_per_cell": max(r["run_index"] for r in rows) + 1,
        "arms": {arm: arm_summary(arm_rows) for arm, arm_rows in sorted(by_arm.items())},
        "by_task": {
            task: {
                arm: arm_summary(by_arm_task[(arm, task)])
                for arm in sorted(by_arm)
            }
            for task in tasks
        },
        "paired_differences": {
            "note": "subject minus control, paired by (task_id, run_index); "
                    "an interval crossing zero means no measurable difference",
            "seed": SEED,
            "replicates": REPLICATES,
            "overall": {m: difference(rows, m) for m in ["wall_time_s", "tokens_in", "tokens_out", "cost_usd"]},
            "by_task": {
                task: {m: difference(rows, m, task) for m in ["wall_time_s", "tokens_in", "cost_usd"]}
                for task in tasks
            },
        },
    }

    out_path.write_text(json.dumps(report, indent=2) + "\n")
    print(f"wrote {out_path}")
    for arm, summary in report["arms"].items():
        lo, hi = summary["completion_wilson_95"]
        print(
            f"{arm:24s} {summary['completed']}/{summary['attempts']} "
            f"[{lo:.3f}, {hi:.3f}]  "
            f"median wall {summary['metrics']['wall_time_s']['median']:.3f}s  "
            f"median tokens_in {summary['metrics']['tokens_in']['median']:.0f}  "
            f"cost ${summary['total_cost_usd']:.6f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
