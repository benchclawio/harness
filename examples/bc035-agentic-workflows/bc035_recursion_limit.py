"""How many super-steps will LangGraph actually run before it stops a loop?

No model call. The node does nothing but increment a counter and route back to itself,
so the only thing being measured is the framework's own loop guard.

Run with LangGraph 1.2.11, CPython 3.12.13.
"""

from typing import Annotated, TypedDict

from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph


class State(TypedDict):
    steps: Annotated[int, lambda a, b: a + b]


def work(state: State) -> State:
    return {"steps": 1}


def keep_going(state: State) -> str:
    return "work"  # never terminates on its own


builder = StateGraph(State)
builder.add_node("work", work)
builder.add_edge(START, "work")
builder.add_conditional_edges("work", keep_going, {"work": "work", "done": END})
graph = builder.compile()

try:
    graph.invoke({"steps": 0})
    print("graph terminated on its own - unexpected")
except GraphRecursionError as exc:
    print("GraphRecursionError raised")
    print("message:", str(exc).split("\n")[0][:120])
