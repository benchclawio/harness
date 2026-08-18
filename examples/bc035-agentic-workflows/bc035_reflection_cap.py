"""A reflection loop that terminates because we made it terminate.

The "model" is a deterministic stub, so the example is free to run and produces the same
output every time. The control flow is real LangGraph - only the generation step is faked.

Run with LangGraph 1.2.11, CPython 3.12.13.
"""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

MAX_ATTEMPTS = 3


class State(TypedDict):
    draft: str
    attempts: int
    accepted: bool


def generate(state: State) -> State:
    # Stands in for a model call. Each attempt appends one more clause.
    draft = state["draft"] + f" v{state['attempts'] + 1}"
    return {"draft": draft, "attempts": state["attempts"] + 1}


def critique(state: State) -> State:
    # Stands in for a scoring model or a validator. Accepts on the third attempt.
    return {"accepted": state["attempts"] >= 3}


def route(state: State) -> str:
    if state["accepted"]:
        return "accept"
    if state["attempts"] >= MAX_ATTEMPTS:
        return "give_up"
    return "retry"


builder = StateGraph(State)
builder.add_node("generate", generate)
builder.add_node("critique", critique)
builder.add_edge(START, "generate")
builder.add_edge("generate", "critique")
builder.add_conditional_edges(
    "critique", route, {"retry": "generate", "accept": END, "give_up": END}
)
graph = builder.compile()

final = graph.invoke({"draft": "answer", "attempts": 0, "accepted": False})
print("attempts:", final["attempts"])
print("accepted:", final["accepted"])
print("draft:", final["draft"])
