#!/usr/bin/env python3
"""Offline acceptance tests for the bc-039 machinery.

Stdlib only. No model calls, no network, no SDK installed, no spend. Run with:

    python3 adapters/test_bc039.py

What this proves: the workload issues exactly the ground truth the frozen suite declares,
injected errors survive as errors without aborting the run, nesting is recorded, and the
capture arithmetic detects drops, mis-parenting, duplicates and error-record loss — because
each of those is deliberately simulated here with a lossy fake backend.

What this cannot prove: that the real Langfuse and Phoenix SDKs are wired up correctly. Only
the positive-control gate on the sandbox can prove that, which is why the protocol makes it a
blocking gate rather than a checklist item.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bc039_capture import compare, compare_tokens, wilson  # noqa: E402
from bc039_runner import ROOT, count_issued, run_workload  # noqa: E402

SUITE = json.loads((ROOT / "methodology/bc039-workload-v0.1.0.json").read_text())

PASSED = 0
FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASSED
    if condition:
        PASSED += 1
    else:
        FAILED.append(f"{name}{(' — ' + detail) if detail else ''}")


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

class RecordingSpan:
    def __init__(self, backend, name, kind, parent, attributes):
        self.backend = backend
        self.name = name
        self.kind = kind
        self.parent = parent
        self.attributes = dict(attributes)
        self.has_error = False
        self.ended = False

    def set_attribute(self, key, value):
        self.attributes[key] = value

    def record_error(self, exc):
        self.has_error = True

    def end(self):
        self.ended = True
        self.backend.finished.append(self)


class RecordingTracer:
    """A perfect backend: captures everything, nests correctly, loses nothing."""

    def __init__(self):
        self.finished: list[RecordingSpan] = []

    def start_span(self, name, kind, parent, attributes):
        return RecordingSpan(self, name, kind, parent, attributes)

    def exported(self):
        records = []
        for span in self.finished:
            records.append(
                {
                    "run_id": span.attributes["benchclaw.run_id"],
                    "step_index": span.attributes["benchclaw.step_index"],
                    "parent_step_index": (
                        span.parent.attributes["benchclaw.step_index"] if span.parent else None
                    ),
                    "kind": span.attributes["benchclaw.kind"],
                    "has_error": span.has_error,
                    "tokens_in": span.attributes.get("benchclaw.tokens_in"),
                    "tokens_out": span.attributes.get("benchclaw.tokens_out"),
                }
            )
        return records


def fake_model(prompt, context):
    """Deterministic model test double. Zero paid calls."""
    return {"text": f"ok:{context['step']}", "tokens_in": 11, "tokens_out": 3}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_issued_matches_frozen_ground_truth():
    tracer = RecordingTracer()
    result = run_workload(tracer, fake_model, suite=SUITE, run_id="run-a")
    expected = SUITE["ground_truth"]["per_run_totals"]
    actual = result["issued_counts"]
    for key in ("llm", "tool", "retrieval", "spans", "nested_edges", "errors"):
        check(
            f"issued {key} == frozen ground truth",
            actual[key] == expected[key],
            f"issued {actual[key]}, declared {expected[key]}",
        )
    check("every span ended", all(s.ended for s in tracer.finished))
    check("span count matches issued", len(tracer.finished) == expected["spans"])


def test_injected_errors_do_not_abort_the_run():
    tracer = RecordingTracer()
    result = run_workload(tracer, fake_model, suite=SUITE, run_id="run-b")
    errored = [r for r in result["issued"] if r["errored"]]
    check("two injected errors recorded", len(errored) == 2, f"got {len(errored)}")
    check("all errored steps were expected", all(r["expected_error"] for r in errored))
    # The steps after an injected failure are part of the denominator too.
    tool_error = next(r for r in errored if r["scenario"] == "tool-error")
    after = [
        r
        for r in result["issued"]
        if r["scenario"] == "tool-error" and r["step_index"] > tool_error["step_index"]
    ]
    check("scenario continues past an injected tool failure", len(after) == 2, f"got {len(after)}")


def test_perfect_backend_scores_perfect_but_not_certain():
    tracer = RecordingTracer()
    result = run_workload(tracer, fake_model, suite=SUITE, run_id="run-c")
    report = compare(result["issued"], tracer.exported())
    check("llm capture 100%", report["capture"]["llm"]["rate"] == 1.0)
    check("tool capture 100%", report["capture"]["tool"]["rate"] == 1.0)
    check("retrieval capture 100%", report["capture"]["retrieval"]["rate"] == 1.0)
    check("nesting 100%", report["nesting"]["rate"] == 1.0)
    check("errors 100%", report["errors"]["rate"] == 1.0)
    check("nothing missing", report["missing_spans"] == [])
    # The honest-statistics requirement: a perfect sample must not claim certainty.
    check(
        "perfect capture still has a CI lower bound below 1.0",
        report["capture_all_spans"]["ci95_low"] < 1.0,
        str(report["capture_all_spans"]),
    )


def test_dropped_span_is_detected_and_named():
    tracer = RecordingTracer()
    result = run_workload(tracer, fake_model, suite=SUITE, run_id="run-d")
    exported = tracer.exported()
    victim = next(r for r in exported if r["kind"] == "retrieval")
    lossy = [r for r in exported if r is not victim]

    report = compare(result["issued"], lossy)
    check("retrieval capture drops below 1.0", report["capture"]["retrieval"]["rate"] < 1.0)
    check("exactly one span reported missing", len(report["missing_spans"]) == 1)
    named = report["missing_spans"][0]
    check(
        "the missing span is named individually",
        named["step_index"] == victim["step_index"] and named["kind"] == "retrieval",
        json.dumps(named),
    )
    check("llm capture unaffected", report["capture"]["llm"]["rate"] == 1.0)


def test_flattened_trace_is_caught():
    """A flat trace is captured-but-useless; capture rate alone would call it perfect."""
    tracer = RecordingTracer()
    result = run_workload(tracer, fake_model, suite=SUITE, run_id="run-e")
    flattened = [dict(r, parent_step_index=None) for r in tracer.exported()]

    report = compare(result["issued"], flattened)
    check("capture still reads 100% on a flat trace", report["capture_all_spans"]["rate"] == 1.0)
    check("nesting correctly reads 0%", report["nesting"]["rate"] == 0.0)
    check(
        "every broken edge is named",
        len(report["nesting_wrong"]) == SUITE["ground_truth"]["per_run_totals"]["nested_edges"],
        f"got {len(report['nesting_wrong'])}",
    )


def test_error_record_loss_is_separated_from_span_loss():
    tracer = RecordingTracer()
    result = run_workload(tracer, fake_model, suite=SUITE, run_id="run-f")
    silenced = [dict(r, has_error=False) for r in tracer.exported()]

    report = compare(result["issued"], silenced)
    check("all spans still captured", report["capture_all_spans"]["rate"] == 1.0)
    check("error capture reads 0%", report["errors"]["rate"] == 0.0)
    check("both lost error records named", len(report["errors_missing"]) == 2)
    check(
        "reason distinguishes present-but-silent from absent",
        all(r["reason"] == "span present, error not recorded" for r in report["errors_missing"]),
    )


def test_duplicate_records_are_counted_not_credited():
    tracer = RecordingTracer()
    result = run_workload(tracer, fake_model, suite=SUITE, run_id="run-g")
    exported = tracer.exported()
    report = compare(result["issued"], exported + exported[:3])
    check("duplicates counted", report["duplicate_exported_records"] == 3)
    check("duplicates do not inflate capture", report["capture_all_spans"]["rate"] == 1.0)


def test_token_mismatch_is_detected():
    tracer = RecordingTracer()
    result = run_workload(tracer, fake_model, suite=SUITE, run_id="run-h")
    exported = tracer.exported()
    provider = {"tokens_in": result["tokens_in"], "tokens_out": result["tokens_out"]}

    agreeing = compare_tokens(result["issued"], exported, provider)
    check("token totals match the provider", agreeing["tokens_in_match"] and agreeing["tokens_out_match"])
    # 10 LLM spans are issued but only 9 can carry usage: `llm-error`'s doomed call raises
    # before the model is reached, so there is no usage to report. The token-matching
    # denominator must exclude it, or a correct tool would look like it dropped a figure.
    check(
        "9 of 10 llm spans carry token data; the failed call has no usage",
        agreeing["llm_spans_with_token_data"] == 9,
        str(agreeing["llm_spans_with_token_data"]),
    )

    tampered = [dict(r, tokens_in=(r["tokens_in"] - 1) if r["tokens_in"] else r["tokens_in"]) for r in exported]
    disagreeing = compare_tokens(result["issued"], tampered, provider)
    check("a token discrepancy is detected", not disagreeing["tokens_in_match"])


def test_wilson_boundaries():
    perfect = wilson(400, 400)
    check("400/400 lower bound is below 1", perfect["ci95_low"] < 1.0)
    check("400/400 lower bound is near 0.99", 0.985 < perfect["ci95_low"] < 0.995, str(perfect))
    check("empty denominator is None, not a crash", wilson(0, 0)["rate"] is None)
    half = wilson(50, 100)
    check("50/100 straddles 0.5", half["ci95_low"] < 0.5 < half["ci95_high"])


def test_run_ids_do_not_collide():
    """Correlation is (run_id, step_index); two runs must not alias onto each other."""
    tracer_a, tracer_b = RecordingTracer(), RecordingTracer()
    a = run_workload(tracer_a, fake_model, suite=SUITE, run_id="run-i")
    b = run_workload(tracer_b, fake_model, suite=SUITE, run_id="run-j")
    # Feeding run A's issued spans B's exported records must score zero, not 100%.
    report = compare(a["issued"], tracer_b.exported())
    check("cross-run records do not count as captured", report["capture_all_spans"]["rate"] == 0.0)
    check("step indices are stable across runs", [r["step_index"] for r in a["issued"]] == [r["step_index"] for r in b["issued"]])


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    total = PASSED + len(FAILED)
    print(json.dumps({"passed": PASSED, "failed": len(FAILED), "total": total}, indent=2))
    for failure in FAILED:
        print(f"FAIL: {failure}")
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
