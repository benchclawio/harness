#!/usr/bin/env python3
"""Offline tests for the repaired corpus and request ledger."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from bc038_openai_ledger_proxy import State, enforce_request_payload, ledger_record


def test_request_enforcement() -> None:
    original = {
        "model": "gpt-4o",
        "temperature": 1,
        "messages": [{"role": "user", "content": "private prompt"}],
    }
    forwarded, model, temperature = enforce_request_payload(original, "gpt-4o-2024-08-06")
    assert original["model"] == "gpt-4o" and original["temperature"] == 1
    assert forwarded["model"] == "gpt-4o-2024-08-06" and forwarded["temperature"] == 0
    assert model == "gpt-4o" and temperature == 1
    try:
        enforce_request_payload({"stream": True}, "gpt-4o-2024-08-06")
        raise AssertionError("streaming should be rejected")
    except ValueError:
        pass


def test_prompt_free_ledger() -> None:
    response = {
        "id": "chatcmpl-test",
        "model": "gpt-4o-2024-08-06",
        "system_fingerprint": "fp_test",
        "choices": [{"message": {"content": "pass"}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 2, "total_tokens": 102},
    }
    row = ledger_record(
        arm="test",
        path="/v1/chat/completions",
        status=200,
        original_model="gpt-4o",
        original_temperature=None,
        enforced_model="gpt-4o-2024-08-06",
        response_payload=response,
        wall_time_s=1.23456789,
    )
    assert row["prompt_tokens"] == 100 and row["completion_tokens"] == 2
    assert "choices" not in row and "messages" not in row
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "ledger.jsonl"
        state = State("test", "https://example.invalid", path, "gpt-4o-2024-08-06")
        state.set_context("arith-01-wrong")
        state.append(row)
        saved = json.loads(path.read_text())
        assert saved["context"] == "arith-01-wrong" and saved["sequence"] == 1
        assert "private prompt" not in path.read_text() and "Bearer" not in path.read_text()


def test_repaired_corpus() -> None:
    corpus = json.loads(Path("bc038-corpus-v0.2.0.json").read_text())
    by_id = {case["case_id"]: case for case in corpus["cases"]}
    assert corpus["counts"]["total"] == 70
    for wrong in [c for c in corpus["cases"] if c.get("defect_class") == "wrong_tool_sequence"]:
        correct = by_id[wrong["matched_with"]]
        assert wrong["agent_output"] == correct["agent_output"]
        assert wrong["tools_offered"] == correct["tools_offered"]
        assert len(correct["trajectory"]) == len(wrong["trajectory"]) + 1
        assert correct["trajectory"][-1]["tool"] == "price_lookup"
    for case in corpus["cases"]:
        if case["source_task_id"].startswith("fmt-"):
            assert any(
                step["tool"] == "policy_lookup" and "twice" in step["result"]["text"]
                for step in case["trajectory"]
            )


if __name__ == "__main__":
    test_request_enforcement()
    test_prompt_free_ledger()
    test_repaired_corpus()
    print("bc038 v0.2 offline tests passed")
