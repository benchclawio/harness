"""A LangGraph agent loop that never imports `langchain`, only `langchain_core`.

Demonstrates the point of the article: LangGraph is the runtime, langchain-core supplies the
primitives, and the `langchain` umbrella package is not involved at all.

Deterministic, offline, no model calls, no API key, no cost. The "model" is a plain function
so the output is byte-identical on every run.

Run:
    .venvs/langgraph/bin/python3 operations/demo_langgraph_without_langchain.py
"""

from __future__ import annotations

import json
import sys
from typing import Annotated, TypedDict

# Only langchain_core - the umbrella `langchain` package is never imported.
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages


class State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    attempts: int


def call_model(state: State) -> dict:
    """Stand-in for a chat model. Asks for a tool call on the first pass only."""
    attempts = state["attempts"] + 1
    if attempts == 1:
        return {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "lookup_order", "args": {"order_id": "A-1042"}, "id": "call_1"}
                    ],
                )
            ],
            "attempts": attempts,
        }
    last = state["messages"][-1]
    return {"messages": [AIMessage(content=f"Order status: {last.content}")], "attempts": attempts}


def call_tool(state: State) -> dict:
    call = state["messages"][-1].tool_calls[0]
    return {
        "messages": [ToolMessage(content="shipped", tool_call_id=call["id"], name=call["name"])]
    }


def should_continue(state: State) -> str:
    """The cycle: back to the model after a tool call, otherwise stop."""
    last = state["messages"][-1]
    return "tools" if getattr(last, "tool_calls", None) else END


builder = StateGraph(State)
builder.add_node("model", call_model)
builder.add_node("tools", call_tool)
builder.add_edge(START, "model")
builder.add_conditional_edges("model", should_continue, {"tools": "tools", END: END})
builder.add_edge("tools", "model")  # the loop LangChain's linear chains cannot express
graph = builder.compile()

result = graph.invoke({"messages": [HumanMessage(content="Where is order A-1042?")], "attempts": 0})

print(
    json.dumps(
        {
            "python": sys.version.split()[0],
            "langchain_umbrella_imported": "langchain" in sys.modules,
            "langchain_core_imported": "langchain_core" in sys.modules,
            "model_calls": result["attempts"],
            "message_types": [type(m).__name__ for m in result["messages"]],
            "final_answer": result["messages"][-1].content,
        },
        indent=2,
    )
)
