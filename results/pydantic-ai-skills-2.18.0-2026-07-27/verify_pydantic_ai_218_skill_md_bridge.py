"""Executed source for the code samples in /pydantic-ai-skills/.

Shows the DIY bridge: Pydantic AI 2.18.0 has no SKILL.md reader, but an
agentskills.io-format skill file can be parsed and mounted as a deferred
Capability in a few lines.

Offline: FunctionModel, no network calls, no cost. Async tools throughout —
sync fakes hang under 2.18.0 in this runtime.
"""

import asyncio
import json
import re
import tempfile
from pathlib import Path

import pydantic_ai
from pydantic_ai import Agent
from pydantic_ai.capabilities import Capability
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

SKILL_MD = """---
name: refunds
description: Use for refund eligibility, refund status, or processing a refund.
---

# Refunds

Always confirm the order ID before issuing a refund.
"""


def load_skill(path: Path) -> Capability:
    """Parse an agentskills.io SKILL.md into a deferred Pydantic AI capability."""
    text = path.read_text()
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not match:
        raise ValueError(f"{path} has no YAML frontmatter")
    front, body = match.groups()
    meta = dict(
        (k.strip(), v.strip())
        for k, _, v in (line.partition(":") for line in front.splitlines())
        if k.strip()
    )
    return Capability(
        id=meta["name"],
        description=meta["description"],
        instructions=body.strip(),
        defer_loading=True,
    )


results: dict[str, object] = {"version": pydantic_ai.__version__}
seen: list[list[str]] = []


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        skill_path = Path(tmp) / "SKILL.md"
        skill_path.write_text(SKILL_MD)

        refunds = load_skill(skill_path)
        results["parsed_id"] = refunds.id
        results["parsed_description"] = refunds.description
        results["defer_loading"] = refunds.defer_loading

        @refunds.tool_plain
        async def refund_status(order_id: str) -> str:
            """Look up the refund status for an order."""
            return f"Order {order_id}: refund issued."

        captured_instructions: list[str] = []

        async def capture(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            seen.append(sorted(t.name for t in (info.function_tools or [])))
            for m in messages:
                if getattr(m, "instructions", None):
                    captured_instructions.append(m.instructions)
            if len(seen) == 1:
                return ModelResponse(parts=[ToolCallPart("load_capability", {"id": "refunds"})])
            return ModelResponse(parts=[TextPart("Order ABC-123: refund issued.")])

        agent = Agent(
            FunctionModel(capture),
            instructions="You are a support assistant.",
            capabilities=[refunds],
        )
        run = await agent.run("What is the status of order ABC-123?")

        instr = captured_instructions[0] if captured_instructions else ""
        results["catalog_entry_present"] = "refunds:" in instr
        results["skill_body_absent_before_load"] = "confirm the order ID" not in instr
        results["load_capability_offered"] = "load_capability" in seen[0]
        results["model_requests"] = len(seen)
        results["final_output"] = run.output

        # Prove the loaded instructions arrived as the load_capability tool RESULT.
        returns = [
            part.content
            for m in run.all_messages()
            for part in getattr(m, "parts", [])
            if getattr(part, "tool_name", None) == "load_capability"
            and hasattr(part, "content")
        ]
        results["instructions_returned_as_tool_result"] = any(
            "confirm the order ID" in str(r) for r in returns
        )

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
