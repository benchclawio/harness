#!/usr/bin/env python3
"""bc-039 capture comparison: issued spans (ours) against exported records (the tool's).

Tool-agnostic on purpose. Each per-tool reader in `bc039_exporters.py` normalises whatever
its API returns into one flat record shape, and every arithmetic decision then happens here,
once. That way a capture figure cannot differ between arms because of how its reader was
written.

Normalised exported record:
    {"run_id": str, "step_index": int, "parent_step_index": int|None,
     "kind": "llm"|"tool"|"retrieval", "has_error": bool,
     "tokens_in": int|None, "tokens_out": int|None}

Stdlib only, so the arithmetic is testable without any SDK installed.
"""

from __future__ import annotations

import math

LLM = "llm"
TOOL = "tool"
RETRIEVAL = "retrieval"
SIGNALS = (LLM, TOOL, RETRIEVAL)


def wilson(successes: int, total: int, z: float = 1.959963985) -> dict:
    """Wilson score interval for a proportion.

    Capture rate is a proportion, so a proportion interval is required. The bootstrap used
    elsewhere in this harness is for differences of means and would be a category error here.

    Wilson is chosen over the normal approximation precisely because the interesting cases
    sit at the boundary: at 400/400 the normal approximation returns a zero-width interval,
    which would let the copy imply a perfect score is proven. Wilson returns a lower bound
    near 0.990, which is the honest statement a 400-opportunity sample supports.
    """
    if total == 0:
        return {"rate": None, "ci95_low": None, "ci95_high": None, "n": 0}
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    margin = (z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))) / denominator
    return {
        "rate": round(p, 6),
        "ci95_low": round(max(0.0, centre - margin), 6),
        "ci95_high": round(min(1.0, centre + margin), 6),
        "n": total,
        "successes": successes,
    }


def compare(issued: list[dict], exported: list[dict]) -> dict:
    """Compare one arm's issued spans against what its backend actually returned."""
    by_key = {(record["run_id"], record["step_index"]): record for record in exported}
    # A backend returning the same span twice is a defect, not a bonus. Count it.
    duplicates = len(exported) - len(by_key)

    captured = {signal: 0 for signal in SIGNALS}
    totals = {signal: 0 for signal in SIGNALS}
    missing: list[dict] = []

    nesting_correct = 0
    nesting_total = 0
    nesting_wrong: list[dict] = []

    errors_captured = 0
    errors_total = 0
    errors_missing: list[dict] = []

    for record in issued:
        key = (record["run_id"], record["step_index"])
        kind = record["kind"]
        totals[kind] += 1
        found = by_key.get(key)

        if found is None:
            # Named individually, as the addendum requires. A bare count cannot tell a
            # reader which span went missing or under what conditions.
            missing.append(
                {
                    "run_id": record["run_id"],
                    "step_index": record["step_index"],
                    "scenario": record["scenario"],
                    "kind": kind,
                    "name": record["name"],
                    "expected_error": record["expected_error"],
                }
            )
        else:
            captured[kind] += 1

        if record["parent_step_index"] is not None:
            nesting_total += 1
            if found is not None:
                if found.get("parent_step_index") == record["parent_step_index"]:
                    nesting_correct += 1
                else:
                    nesting_wrong.append(
                        {
                            "run_id": record["run_id"],
                            "step_index": record["step_index"],
                            "scenario": record["scenario"],
                            "expected_parent": record["parent_step_index"],
                            "reported_parent": found.get("parent_step_index"),
                        }
                    )

        if record["errored"]:
            errors_total += 1
            if found is not None and found.get("has_error"):
                errors_captured += 1
            else:
                errors_missing.append(
                    {
                        "run_id": record["run_id"],
                        "step_index": record["step_index"],
                        "scenario": record["scenario"],
                        "name": record["name"],
                        "reason": "span absent" if found is None else "span present, error not recorded",
                    }
                )

    return {
        "capture": {signal: wilson(captured[signal], totals[signal]) for signal in SIGNALS},
        "capture_all_spans": wilson(sum(captured.values()), sum(totals.values())),
        "nesting": wilson(nesting_correct, nesting_total),
        "errors": wilson(errors_captured, errors_total),
        "missing_spans": missing,
        "nesting_wrong": nesting_wrong,
        "errors_missing": errors_missing,
        "duplicate_exported_records": duplicates,
    }


def compare_tokens(issued: list[dict], exported: list[dict], reported: dict) -> dict:
    """Do the tool's token figures match what the provider itself reported?

    A tracing tool that invents or rounds token counts is a specific, nameable failure and is
    reported separately from span capture. `reported` is the provider's own usage for the run.
    """
    by_key = {(r["run_id"], r["step_index"]): r for r in exported}
    tool_in = 0
    tool_out = 0
    seen = 0
    for record in issued:
        if record["kind"] != LLM:
            continue
        found = by_key.get((record["run_id"], record["step_index"]))
        if found is None or found.get("tokens_in") is None:
            continue
        seen += 1
        tool_in += int(found.get("tokens_in") or 0)
        tool_out += int(found.get("tokens_out") or 0)

    return {
        "llm_spans_with_token_data": seen,
        "tool_tokens_in": tool_in,
        "tool_tokens_out": tool_out,
        "provider_tokens_in": reported.get("tokens_in"),
        "provider_tokens_out": reported.get("tokens_out"),
        "tokens_in_match": tool_in == reported.get("tokens_in"),
        "tokens_out_match": tool_out == reported.get("tokens_out"),
    }
