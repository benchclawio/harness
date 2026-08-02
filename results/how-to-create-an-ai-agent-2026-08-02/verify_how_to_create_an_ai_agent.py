"""Execute the complete bc-030 example five times and record exact output."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
EXAMPLE = HERE / "how_to_create_an_ai_agent_example.py"
OUTPUT = HERE / "how-to-create-an-ai-agent-example-output-2026-08-02.json"


runs: list[str] = []
for _ in range(5):
    completed = subprocess.run(
        [sys.executable, str(EXAMPLE)],
        check=True,
        capture_output=True,
        text=True,
    )
    runs.append(completed.stdout)

if len(set(runs)) != 1:
    raise AssertionError("The five executions were not byte-identical")

parsed = json.loads(runs[0])
if parsed["happy_path"]["tool_calls"] != 1:
    raise AssertionError("Happy path did not execute exactly one tool")
if parsed["unknown_tool"] != "Blocked tool: delete_order":
    raise AssertionError("Unknown tool did not fail closed")
if parsed["step_limit"] != "Stopped after 3 steps without a final answer":
    raise AssertionError("Step limit did not stop the endless model")

record = {
    "executed_at": "2026-08-02",
    "executions": len(runs),
    "byte_identical": True,
    "model_api_calls": 0,
    "model_cost_usd": 0.0,
    "stdout_sha256": hashlib.sha256(runs[0].encode()).hexdigest(),
    "stdout": parsed,
}
OUTPUT.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
print(json.dumps(record, indent=2))

