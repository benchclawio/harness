from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from benchclaw_harness.analysis import bootstrap_interval, wilson_interval
from benchclaw_harness.real_pilot import (
    ToolRuntime,
    load_real_pilot_suite,
    score_real_pilot_task,
)
from benchclaw_harness.redaction import sanitize_message, scan_public_value
from benchclaw_harness.runner import run_fixture_pilot
from benchclaw_harness.validation import validate_event, verify_bundle


ROOT = Path(__file__).resolve().parents[1]
REAL_PILOT_SUITE = ROOT.parent / "methodology/real-pilot-task-suite-v0.1.0.json"


class HarnessTest(unittest.TestCase):
    def test_fixture_pilot_runs_and_verifies(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "bundle"
            result = run_fixture_pilot(ROOT / "config/fixture-pilot-v1.json", bundle)
            self.assertEqual(result["events"], 40)
            self.assertEqual(verify_bundle(bundle)["events"], 40)
            analysis = json.loads((bundle / "analysis.json").read_text(encoding="utf-8"))
            self.assertFalse(analysis["publication_eligible"])
            self.assertEqual(len(analysis["comparisons"]), 1)

    def test_redaction_scan_and_sanitizer(self) -> None:
        findings = scan_public_value(
            {"authorization": "Bearer definitely-secret-value", "note": "person@example.com"}
        )
        self.assertGreaterEqual(len(findings), 2)
        sanitized = sanitize_message("Bearer definitely-secret-value person@example.com")
        self.assertNotIn("definitely-secret-value", sanitized)
        self.assertNotIn("person@example.com", sanitized)

    def test_statistics_helpers(self) -> None:
        interval = wilson_interval(8, 10)
        self.assertIsNotNone(interval)
        assert interval is not None
        self.assertLess(interval[0], 0.8)
        self.assertGreater(interval[1], 0.8)
        paired = [(1.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 0.0)]
        bootstrap = bootstrap_interval(paired, lambda values: sum(values) / len(values), 7, 500, 0.95)
        self.assertIsNotNone(bootstrap)

    def test_bundle_tamper_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "bundle"
            run_fixture_pilot(ROOT / "config/fixture-pilot-v1.json", bundle)
            with (bundle / "events.jsonl").open("a", encoding="utf-8") as handle:
                handle.write("{}\n")
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                verify_bundle(bundle)

    def test_invalid_metric_is_rejected(self) -> None:
        event = {
            "schema_version": "1.0.0",
            "event_id": "evt:12345678",
            "run_id": "run-1",
            "recorded_at": "2026-07-23T00:00:00Z",
            "publication_eligible": False,
            "subject": {"id": "a", "version": "1", "adapter": "x", "adapter_version": "1"},
            "task": {
                "suite_id": "s",
                "suite_version": "1",
                "id": "t",
                "input_sha256": "a" * 64,
            },
            "pair": {"key": "p", "run_index": 0, "order_index": 0},
            "model": {"provider": "local", "id": "fixture", "temperature": 0},
            "environment": {
                "harness_version": "1",
                "python_version": "3",
                "platform": "test",
                "region": "local",
            },
            "parameters": {"seed": 1, "timeout_s": 1},
            "outcome": {"status": "success", "completed": True},
            "metrics": {
                "tokens_in": -1,
                "tokens_out": 0,
                "cost_usd": 0,
                "wall_time_s": 0,
                "tool_calls": 0,
            },
            "failure": None,
            "provenance": {
                "config_sha256": "b" * 64,
                "task_suite_sha256": "c" * 64,
                "source_revision": "test",
            },
        }
        self.assertTrue(any("tokens_in" in error for error in validate_event(event)))

    def test_real_pilot_reference_traces_score(self) -> None:
        suite = load_real_pilot_suite(REAL_PILOT_SUITE)
        for task in suite["tasks"]:
            with self.subTest(task=task["id"]):
                runtime = ToolRuntime(task)
                for call in task["reference_trace"]:
                    runtime.call(call["tool"], call["arguments"])
                score = score_real_pilot_task(task, runtime, task["expected_output"])
                self.assertTrue(score["completed"], score["errors"])

    def test_real_pilot_stale_revision_is_model_directed(self) -> None:
        suite = load_real_pilot_suite(REAL_PILOT_SUITE)
        task = next(task for task in suite["tasks"] if task["id"] == "recover-stale-revision")
        runtime = ToolRuntime(task)
        first = runtime.call("count_active_items", {"bucket": "C", "revision": "r1"})
        self.assertEqual(first["error_code"], "stale_revision")
        second = runtime.call(
            "count_active_items",
            {"bucket": "C", "revision": first["required_revision"]},
        )
        self.assertEqual(second["active_count"], 4)

    def test_real_pilot_route_token_is_stateful(self) -> None:
        suite = load_real_pilot_suite(REAL_PILOT_SUITE)
        task = next(task for task in suite["tasks"] if task["id"] == "dependent-shipping-quote")
        runtime = ToolRuntime(task)
        rejected = runtime.call(
            "quote_shipping_route",
            {"route_token": "route:NBO:FRA:Z4", "weight_kg": 3.5},
        )
        self.assertEqual(rejected["error_code"], "route_token_not_issued")

    def test_real_pilot_forbidden_tool_fails(self) -> None:
        suite = load_real_pilot_suite(REAL_PILOT_SUITE)
        task = next(task for task in suite["tasks"] if task["id"] == "refund-policy-minimal-tools")
        runtime = ToolRuntime(task)
        runtime.call("customer_profile", {"order_id": "O-1047"})
        score = score_real_pilot_task(task, runtime, task["expected_output"])
        self.assertFalse(score["completed"])
        self.assertIn("forbidden tool was called", score["errors"])

    def test_real_pilot_final_output_is_strict(self) -> None:
        suite = load_real_pilot_suite(REAL_PILOT_SUITE)
        task = suite["tasks"][0]
        runtime = ToolRuntime(task)
        for call in task["reference_trace"]:
            runtime.call(call["tool"], call["arguments"])
        output = {**task["expected_output"], "extra": "not allowed"}
        score = score_real_pilot_task(task, runtime, output)
        self.assertFalse(score["completed"])


if __name__ == "__main__":
    unittest.main()
