"""State that survives between invocations, which is what makes a workflow resumable.

No model call. Two separate invokes against the same thread id; the second one sees what
the first one wrote.

Run with LangGraph 1.2.11, langgraph-checkpoint 4.2.0, CPython 3.12.13.
"""

from typing import Annotated, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph


class State(TypedDict):
    seen: Annotated[list[str], lambda a, b: a + b]


def step(state: State) -> State:
    return {"seen": [f"call-{len(state['seen']) + 1}"]}


builder = StateGraph(State)
builder.add_node("step", step)
builder.add_edge(START, "step")
builder.add_edge("step", END)
graph = builder.compile(checkpointer=InMemorySaver())

config = {"configurable": {"thread_id": "order-4471"}}
print("first :", graph.invoke({"seen": []}, config)["seen"])
print("second:", graph.invoke({"seen": []}, config)["seen"])
print("state :", graph.get_state(config).values["seen"])
