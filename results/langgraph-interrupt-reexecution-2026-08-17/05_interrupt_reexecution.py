"""bc-036 tutorial snippet 5 — the interrupt() detail that bites people.

Does the interrupted node resume mid-function, or restart from its first line?
This is the question every human-in-the-loop tutorial skips. Run it and find out.

Run: .venvs/langgraph-1.2.11/bin/python operations/bc036/05_interrupt_reexecution.py
Pinned: langgraph==1.2.11
"""

from typing import Annotated, TypedDict
from operator import add

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

side_effects: list[str] = []


class State(TypedDict):
    log: Annotated[list[str], add]


def review(state: State) -> dict:
    # Anything above interrupt() is not protected. Put a charge, an email or a
    # database write here and it happens once per resume, not once per run.
    side_effects.append("charged the card")
    decision = interrupt("approve or reject?")
    return {"log": [f"decision={decision}"]}


builder = StateGraph(State)
builder.add_node("review", review)
builder.add_edge(START, "review")
builder.add_edge("review", END)

graph = builder.compile(checkpointer=InMemorySaver())
config = {"configurable": {"thread_id": "side-effect-demo"}}

graph.invoke({"log": []}, config)
print("after the pause,  side effects:", side_effects)

graph.invoke(Command(resume="approve"), config)
print("after the resume, side effects:", side_effects)
print()
print("times the pre-interrupt code ran:", len(side_effects))
