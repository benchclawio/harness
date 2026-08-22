import asyncio
import importlib.metadata
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode


class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


async def main() -> None:
    client = MultiServerMCPClient(
        {
            "math": {
                "url": "http://127.0.0.1:18765/mcp",
                "transport": "http",
            }
        }
    )
    tools = await client.get_tools()

    async def scripted_model(_: State) -> dict:
        return {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "multiply",
                            "args": {"a": 6, "b": 7},
                            "id": "call_1",
                            "type": "tool_call",
                        }
                    ],
                )
            ]
        }

    builder = StateGraph(State)
    builder.add_node("model", scripted_model)
    builder.add_node("tools", ToolNode(tools))
    builder.add_edge(START, "model")
    builder.add_edge("model", "tools")
    builder.add_edge("tools", END)
    graph = builder.compile()

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="What is 6 multiplied by 7?")]}
    )
    tool_content = result["messages"][-1].content

    print(f"langgraph={importlib.metadata.version('langgraph')}")
    print(
        "langchain-mcp-adapters="
        f"{importlib.metadata.version('langchain-mcp-adapters')}"
    )
    print(f"discovered_tools={[tool.name for tool in tools]}")
    print(f"tool_result={tool_content[0]['text']}")


if __name__ == "__main__":
    asyncio.run(main())

