#!/usr/bin/env python3
"""Analyse the bc-025 scored run.

Comparisons are made only within a transport path — A-chat against B-chat, A-resp against
B-resp. Chat Completions and Responses account for tokens differently, so a cross-path
delta would measure the provider's bookkeeping rather than progressive disclosure.

Confidence intervals are bootstrap percentile intervals (10,000 resamples, fixed seed) on
the difference of means. Run counts are 20 per cell, which is too small to lean on a
normality assumption.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import random
import statistics as stats

ROOT = Path(os.environ.get("BENCHCLAW_ROOT", Path(__file__).resolve().parents[1]))
"""Repository root. Override with BENCHCLAW_ROOT when running from a copy."""
RAW = ROOT / "operations/bc025-scored-raw-2026-08-06.jsonl"
OUT = ROOT / "operations/bc025-scored-analysis-2026-08-06.json"

BOOTSTRAP = 10_000
SEED = 20260806


def bootstrap_ci(control: list[float], treatment: list[float]) -> dict:
    """Percentile CI for mean(treatment) - mean(control)."""
    rng = random.Random(SEED)
    observed = stats.fmean(treatment) - stats.fmean(control)
    diffs = []
    for _ in range(BOOTSTRAP):
        c = [control[rng.randrange(len(control))] for _ in control]
        t = [treatment[rng.randrange(len(treatment))] for _ in treatment]
        diffs.append(stats.fmean(t) - stats.fmean(c))
    diffs.sort()
    return {
        "observed_diff": round(observed, 4),
        "ci95_low": round(diffs[int(0.025 * BOOTSTRAP)], 4),
        "ci95_high": round(diffs[int(0.975 * BOOTSTRAP)], 4),
    }


def summarise(rows: list[dict]) -> dict:
    tin = [r["metrics"]["tokens_in"] for r in rows]
    tout = [r["metrics"]["tokens_out"] for r in rows]
    reqs = [r["metrics"]["model_requests"] for r in rows]
    search = [r["metrics"]["tool_search_calls"] for r in rows]
    cost = [r["metrics"]["cost_usd"] for r in rows]
    wall = [r["outer_wall_time_s"] for r in rows]
    exact = [1.0 if r["score"]["exact_match"] else 0.0 for r in rows]
    tool_ok = [1.0 if r["score"]["correct_tool_used"] else 0.0 for r in rows]
    return {
        "runs": len(rows),
        "tokens_in_mean": round(stats.fmean(tin), 2),
        "tokens_in_median": stats.median(tin),
        "tokens_in_stdev": round(stats.stdev(tin), 2) if len(tin) > 1 else 0.0,
        "tokens_out_mean": round(stats.fmean(tout), 2),
        "model_requests_mean": round(stats.fmean(reqs), 3),
        "tool_search_calls_mean": round(stats.fmean(search), 3),
        "cost_usd_mean": round(stats.fmean(cost), 8),
        "cost_usd_total": round(sum(cost), 8),
        "wall_s_mean": round(stats.fmean(wall), 3),
        "exact_match_rate": round(stats.fmean(exact), 4),
        "correct_tool_rate": round(stats.fmean(tool_ok), 4),
    }


def main() -> None:
    rows = [json.loads(line) for line in RAW.read_text(encoding="utf-8").splitlines() if line.strip()]

    by_cell: dict[str, list[dict]] = {}
    for row in rows:
        by_cell.setdefault(row["cell"], []).append(row)

    cells = {name: summarise(items) for name, items in sorted(by_cell.items())}

    comparisons = {}
    for path, control_id, treatment_id in (("chat", "A-chat", "B-chat"), ("responses", "A-resp", "B-resp")):
        control, treatment = by_cell[control_id], by_cell[treatment_id]
        entry = {"control": control_id, "treatment": treatment_id}
        for metric, extract in (
            ("tokens_in", lambda r: float(r["metrics"]["tokens_in"])),
            ("tokens_out", lambda r: float(r["metrics"]["tokens_out"])),
            ("model_requests", lambda r: float(r["metrics"]["model_requests"])),
            ("cost_usd", lambda r: float(r["metrics"]["cost_usd"])),
            ("wall_s", lambda r: float(r["outer_wall_time_s"])),
        ):
            c = [extract(r) for r in control]
            t = [extract(r) for r in treatment]
            ci = bootstrap_ci(c, t)
            base = stats.fmean(c)
            ci["pct_change"] = round(100.0 * (stats.fmean(t) - base) / base, 2) if base else None
            ci["crosses_zero"] = ci["ci95_low"] <= 0 <= ci["ci95_high"]
            entry[metric] = ci
        comparisons[path] = entry

    failures = [
        {
            "sequence": r["sequence"],
            "cell": r["cell"],
            "task_id": r["task_id"],
            "status": r.get("status"),
            "parse_ok": r["score"].get("parse_ok"),
            "correct_tool_used": r["score"].get("correct_tool_used"),
            "tools_called": r["score"].get("distinct_tools_called"),
        }
        for r in rows
        if not r["score"].get("exact_match")
    ]

    by_task = {}
    for row in rows:
        key = (row["task_id"], row["cell"])
        by_task.setdefault(key, []).append(1.0 if row["score"]["exact_match"] else 0.0)

    analysis = {
        "source_jsonl": str(RAW),
        "total_runs": len(rows),
        "total_cost_usd": round(sum(r["metrics"]["cost_usd"] for r in rows), 8),
        "method": {
            "ci": f"bootstrap percentile, {BOOTSTRAP} resamples, seed {SEED}",
            "comparison_rule": "within transport path only; chat and responses are never compared",
        },
        "cells": cells,
        "comparisons": comparisons,
        "accuracy_by_task_cell": {
            f"{task}|{cell}": round(stats.fmean(vals), 4) for (task, cell), vals in sorted(by_task.items())
        },
        "failure_count": len(failures),
        "failures": failures,
    }
    OUT.write_text(json.dumps(analysis, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"written": str(OUT), "runs": len(rows), "failures": len(failures)}))


if __name__ == "__main__":
    main()
