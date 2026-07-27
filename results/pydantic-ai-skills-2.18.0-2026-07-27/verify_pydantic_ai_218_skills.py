"""Verify how Pydantic AI 2.18.0 actually implements progressive disclosure.

Offline only: uses FunctionModel, makes no network calls and costs nothing.
Tools/callbacks are async — sync fakes hang under 2.18.0 in this runtime.

FunctionModel (not TestModel) is used deliberately: TestModel auto-calls every
visible tool with generated arguments, which makes `load_capability` fail on
retries and tells us nothing about what the model was offered.

Checks:
  1. `Capability(defer_loading=True)` exists and is constructible.
  2. The deferred capability's tool is NOT exposed on the first request.
  3. The framework injects the reserved `load_capability` tool + a catalog line.
  4. After the model loads the capability, its tool becomes visible.
  5. There is no SKILL.md / markdown skill reader anywhere in the package.
"""

import asyncio
import json
import pkgutil

import pydantic_ai
from pydantic_ai import Agent
from pydantic_ai.capabilities import Capability
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

results: dict[str, object] = {"version": pydantic_ai.__version__}
seen: list[dict[str, object]] = []

refunds = Capability(
    id="refunds",
    description="Use for refund eligibility, refund status, or processing a refund.",
    instructions="Always confirm the order ID before issuing a refund.",
    defer_loading=True,
)


@refunds.tool_plain
async def refund_status(order_id: str) -> str:
    """Look up the refund status for an order."""
    return f"Order {order_id}: refund issued."


async def capture(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    """Record the tools offered on each request, then drive one load."""
    tools = sorted(t.name for t in (info.function_tools or []))
    instructions = ""
    for m in messages:
        instructions = getattr(m, "instructions", None) or instructions
    seen.append({"request": len(seen) + 1, "tools_offered": tools})

    if len(seen) == 1:
        results["catalog_line_in_instructions"] = "refunds:" in (instructions or "")
        # Model chooses to open the deferred bundle.
        return ModelResponse(parts=[ToolCallPart("load_capability", {"id": "refunds"})])
    return ModelResponse(parts=[TextPart("done")])


async def main() -> None:
    agent = Agent(
        FunctionModel(capture),
        instructions="You are a support assistant.",
        capabilities=[refunds],
    )
    await agent.run("What is the status of order ABC-123?")

    before = set(seen[0]["tools_offered"])  # type: ignore[index]
    after = set(seen[-1]["tools_offered"])  # type: ignore[index]

    results["requests_observed"] = len(seen)
    results["agentinfo_tools_before_load"] = sorted(before)
    results["agentinfo_tools_after_load"] = sorted(after)
    results["load_capability_tool_present"] = "load_capability" in before
    results["local_search_tools_fallback_present"] = "search_tools" in before

    # IMPORTANT: `AgentInfo.function_tools` lists what the AGENT knows about, not
    # what is serialized into the provider payload. On a non-native provider the
    # deferred tool still appears here and the before/after sets are identical, so
    # this surface cannot answer "was the tool in the prompt?". Any token-saving
    # claim must come from counting real request tokens per provider, not from here.
    results["agentinfo_reflects_deferral"] = before != after
    results["token_claim_measurable_here"] = False

    import pydantic_ai.capabilities as caps

    modules = [m.name for m in pkgutil.iter_modules(caps.__path__)]
    results["capability_module_count"] = len(modules)
    results["skill_modules"] = [m for m in modules if "skill" in m.lower()]
    results["skill_exports"] = [n for n in dir(caps) if "skill" in n.lower()]
    results["native_skill_md_reader"] = bool(results["skill_modules"] or results["skill_exports"])

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
