#!/usr/bin/env python3
"""Validate and analyse the bc-038 evaluator run without changing raw evidence."""

from __future__ import annotations

import hashlib
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path


Z95 = 1.959963984540054
EXPECTED_CORPUS_SHA256 = (
    "19f219b3693f7c74b6ddbf379456845a48cb269c87537ab7577c4dcd1b1c6575"
)
ARMS = ("naive", "phoenix", "deepeval", "opik")


def wilson(successes: int, total: int) -> dict[str, float | int]:
    if total == 0:
        return {"events": successes, "total": total, "rate": None, "low": None, "high": None}
    p = successes / total
    z2 = Z95 * Z95
    den = 1 + z2 / total
    centre = (p + z2 / (2 * total)) / den
    half = Z95 * math.sqrt((p * (1 - p) + z2 / (4 * total)) / total) / den
    return {
        "events": successes,
        "total": total,
        "rate": p,
        "low": max(0.0, centre - half),
        "high": min(1.0, centre + half),
    }


def nearest_rank(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q * len(ordered)) - 1)]


def timing(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "median_s": statistics.median(ordered),
        "p95_s_nearest_rank": nearest_rank(ordered, 0.95),
        "min_s": ordered[0],
        "max_s": ordered[-1],
        "mean_s": statistics.mean(ordered),
        "stdev_s": statistics.stdev(ordered),
    }


def majority(values: list[bool]) -> bool:
    assert len(values) % 2 == 1
    return sum(values) > len(values) / 2


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> None:
    base = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
    corpus_path = base / "bc038-corpus-v0.1.0.json"
    corpus = json.loads(corpus_path.read_text())
    cases = corpus["cases"]
    case_by_id = {case["case_id"]: case for case in cases}

    assert sha256(corpus_path) == EXPECTED_CORPUS_SHA256
    assert len(cases) == 70 and len(case_by_id) == 70
    assert Counter(case["label"] for case in cases) == {"wrong": 35, "correct": 35}

    paired_class: dict[str, str] = {}
    for case in cases:
        if case["label"] == "wrong":
            paired_class[case["case_id"]] = case["defect_class"]
    for case in cases:
        if case["label"] == "correct":
            partner = case_by_id[case["matched_with"]]
            paired_class[case["case_id"]] = partner["defect_class"]

    analysis: dict = {
        "schema_version": "bc038-analysis-v0.1.0",
        "corpus": {
            "path": corpus_path.name,
            "sha256": sha256(corpus_path),
            "cases": len(cases),
            "wrong": 35,
            "correct": 35,
            "wrong_by_class": corpus["counts"]["wrong_by_class"],
            "origin_counts": corpus["origin_counts"],
        },
        "reporting_rule": {
            "primary": (
                "case-level majority verdict across three repeats; Wilson 95% interval; "
                "the case, not the repeated judgment, is the statistical unit"
            ),
            "trial_level": "reported as a secondary audit count only",
            "p95": "nearest-rank",
        },
        "arms": {},
    }

    expected_order = [case["case_id"] for case in cases]
    for arm in ARMS:
        path = base / f"bc038-eval-{arm}.jsonl"
        rows = load_jsonl(path)
        assert len(rows) == 210
        assert all(row["arm"] == arm for row in rows)
        assert all(row["error"] is None and row["verdict_pass"] is not None for row in rows)
        for repeat in (1, 2, 3):
            observed = [row["case_id"] for row in rows if row["repeat"] == repeat]
            assert observed == expected_order

        by_case: defaultdict[str, list[dict]] = defaultdict(list)
        for row in rows:
            by_case[row["case_id"]].append(row)
        assert set(by_case) == set(case_by_id)
        assert all(len(group) == 3 for group in by_case.values())

        case_verdict = {
            case_id: majority([bool(row["verdict_pass"]) for row in group])
            for case_id, group in by_case.items()
        }
        wrong_ids = [case["case_id"] for case in cases if case["label"] == "wrong"]
        correct_ids = [case["case_id"] for case in cases if case["label"] == "correct"]
        false_pass_ids = [case_id for case_id in wrong_ids if case_verdict[case_id]]
        false_fail_ids = [case_id for case_id in correct_ids if not case_verdict[case_id]]

        per_class = {}
        for defect_class in sorted(set(paired_class.values())):
            class_wrong = [i for i in wrong_ids if paired_class[i] == defect_class]
            class_correct = [i for i in correct_ids if paired_class[i] == defect_class]
            class_fp = [i for i in class_wrong if case_verdict[i]]
            class_ff = [i for i in class_correct if not case_verdict[i]]
            per_class[defect_class] = {
                "false_pass": {**wilson(len(class_fp), len(class_wrong)), "case_ids": class_fp},
                "false_fail": {**wilson(len(class_ff), len(class_correct)), "case_ids": class_ff},
            }

        trial_wrong = [row for row in rows if row["true_label"] == "wrong"]
        trial_correct = [row for row in rows if row["true_label"] == "correct"]
        flips = {
            case_id: [row["verdict_pass"] for row in group]
            for case_id, group in by_case.items()
            if len({row["verdict_pass"] for row in group}) > 1
        }

        pair_success = []
        for wrong_id in wrong_ids:
            correct_id = case_by_id[wrong_id]["matched_with"]
            if not case_verdict[wrong_id] and case_verdict[correct_id]:
                pair_success.append(case_by_id[wrong_id]["source_task_id"])

        costs = [row["metrics"]["cost_usd"] for row in rows]
        exact_cost = None if any(value is None for value in costs) else sum(costs)
        tokens_in = [row["metrics"]["tokens_in"] for row in rows]
        tokens_out = [row["metrics"]["tokens_out"] for row in rows]

        arm_result = {
            "raw_file": path.name,
            "sha256": sha256(path),
            "evaluations": len(rows),
            "errors": 0,
            "primary_case_level": {
                "false_pass": {**wilson(len(false_pass_ids), len(wrong_ids)), "case_ids": false_pass_ids},
                "false_fail": {**wilson(len(false_fail_ids), len(correct_ids)), "case_ids": false_fail_ids},
            },
            "trial_level_audit": {
                "false_pass": wilson(sum(bool(row["verdict_pass"]) for row in trial_wrong), len(trial_wrong)),
                "false_fail": wilson(sum(not bool(row["verdict_pass"]) for row in trial_correct), len(trial_correct)),
            },
            "per_class_case_level": per_class,
            "determinism": {
                "verdict_flip_cases": len(flips),
                "total_cases": len(cases),
                "case_verdicts": flips,
            },
            "matched_pairs": {
                "both_labels_correct": len(pair_success),
                "total_pairs": len(wrong_ids),
                "source_task_ids": pair_success,
            },
            "wall_time": timing([row["metrics"]["wall_time_s"] for row in rows]),
            "usage": {
                "exact_cost_usd": exact_cost,
                "tokens_in": None if any(value is None for value in tokens_in) else sum(tokens_in),
                "tokens_out": None if any(value is None for value in tokens_out) else sum(tokens_out),
                "available": exact_cost is not None,
            },
        }

        if arm in ("deepeval", "opik"):
            sensitivity = {}
            for threshold in (0.25, 0.5, 0.75):
                verdicts = {
                    case_id: majority([float(row["raw_score"]) >= threshold for row in group])
                    for case_id, group in by_case.items()
                }
                fp = sum(verdicts[i] for i in wrong_ids)
                ff = sum(not verdicts[i] for i in correct_ids)
                sensitivity[str(threshold)] = {
                    "false_pass": wilson(fp, len(wrong_ids)),
                    "false_fail": wilson(ff, len(correct_ids)),
                }
            arm_result["threshold_sensitivity_case_level"] = sensitivity

        analysis["arms"][arm] = arm_result

    out = base / "bc038-analysis-2026-08-14.json"
    out.write_text(json.dumps(analysis, indent=2) + "\n")
    print(out)


if __name__ == "__main__":
    main()
