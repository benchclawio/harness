#!/usr/bin/env python3
"""Recompute bc-039 capture from the already-ingested spans, with the corrected reader.

Why this exists rather than a re-run: the scored run's spans are still in both backends. The
read-back is a separate step from the workload, so a reader bug is fixable without spending
another 600 model calls. Nothing about the measured workload changes.

The issued-span list is reconstructed deterministically from the frozen suite and the run ids
recorded in the raw JSONL — step index, scenario, kind, name, parent and expected-error are
all pure functions of the suite. The reconstruction is then ASSERTED against the
`issued_counts` that the driver recorded live during the run. If those disagree the script
refuses to produce a result, because a reconstruction that does not match what was recorded
is a fabrication.

Usage: python3 recompute_bc039.py <raw.jsonl> <out.json>
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bc039_capture as capture  # noqa: E402
import bc039_exporters as exporters  # noqa: E402
from bc039_runner import ROOT, count_issued  # noqa: E402

SUITE = json.loads((ROOT / "methodology/bc039-workload-v0.1.0.json").read_text())

LANGFUSE_HOST = "http://127.0.0.1:3000"
PHOENIX_BASE = "http://127.0.0.1:6006"
PHOENIX_PROJECT = "bc039"


def reconstruct_issued(run_id: str) -> list[dict]:
    """Rebuild the issued-span records for one run. Pure function of the frozen suite."""
    issued = []
    step_offset = 0
    for scenario in SUITE["scenarios"]:
        for local_index, step in enumerate(scenario["steps"]):
            issued.append(
                {
                    "run_id": run_id,
                    "step_index": step_offset + local_index,
                    "scenario": scenario["id"],
                    "kind": step["kind"],
                    "name": step["name"],
                    "parent_step_index": None
                    if step["parent"] is None
                    else step_offset + step["parent"],
                    "expected_error": bool(step["fails"]),
                    "errored": bool(step["fails"]),
                }
            )
        step_offset += len(scenario["steps"])
    return issued


def main():
    raw_path, out_path = sys.argv[1], sys.argv[2]

    runs = [json.loads(line) for line in Path(raw_path).read_text().splitlines() if line.strip()]

    issued_by_arm: dict[str, list[dict]] = {}
    for run in runs:
        rebuilt = reconstruct_issued(run["run_id"])
        recorded = run["issued_counts"]
        recomputed = count_issued(rebuilt)
        if recomputed != recorded:
            raise SystemExit(
                f"reconstruction mismatch for {run['run_id']}: "
                f"rebuilt {recomputed} vs recorded {recorded}"
            )
        issued_by_arm.setdefault(run["arm"], []).extend(rebuilt)

    lf_public = os.environ["LANGFUSE_INIT_PROJECT_PUBLIC_KEY"]
    lf_secret = os.environ["LANGFUSE_INIT_PROJECT_SECRET_KEY"]

    exported = {
        "langfuse": exporters.read_langfuse(LANGFUSE_HOST, lf_public, lf_secret),
        "phoenix": exporters.read_phoenix(PHOENIX_BASE, PHOENIX_PROJECT),
    }

    reports = {}
    for arm, records in exported.items():
        report = capture.compare(issued_by_arm[arm], records)
        report["exported_record_count"] = len(records)
        reports[arm] = report

    # Overhead against the mandatory uninstrumented control, same-session and interleaved.
    wall = {}
    for run in runs:
        wall.setdefault(run["arm"], []).append(run["wall_time_s"])

    summary = {
        "source_raw": raw_path,
        "reconstruction_verified": True,
        "runs_per_arm": {arm: len(v) // 20 for arm, v in issued_by_arm.items()},
        "issued_totals": {arm: count_issued(v) for arm, v in issued_by_arm.items()},
        "capture": reports,
        "wall_time_s": {
            arm: {
                "n": len(v),
                "mean": round(sum(v) / len(v), 4),
                "min": round(min(v), 4),
                "max": round(max(v), 4),
            }
            for arm, v in wall.items()
        },
        "cost_usd_total": round(sum(r["cost_usd"] for r in runs), 6),
        "provider_requests_total": sum(r["provider_requests"] for r in runs),
    }
    Path(out_path).write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary["capture"], indent=2)[:2000])
    print(json.dumps({k: summary[k] for k in ("wall_time_s", "cost_usd_total", "provider_requests_total")}, indent=2))


if __name__ == "__main__":
    main()
