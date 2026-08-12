#!/usr/bin/env python3
"""Generate the frozen bc-039 workload suite and its ground truth.

Deterministic and offline. No model calls, no network, no randomness — running this twice
produces byte-identical output, so the suite SHA in the manifest is meaningful.

WHY THE AGENT IS SCRIPTED, NOT MODEL-DRIVEN
-------------------------------------------
Cluster three's primary outcome is capture rate against a denominator we own. If the model
decided how many tool calls to issue, the denominator would vary per run and per arm, and
"3 of 4 tool spans captured" could mean the SDK dropped one or that the model simply made
three calls. Those are different findings and a benchmark that cannot separate them is
worthless.

So the control flow is fixed by this file. The model is called at scripted points and its
output is recorded, but nothing the model returns changes how many spans the workload emits.
Every count below is therefore an exact integer known before the run starts, which is the
whole reason this cluster is measurable at all.

The trade-off is stated plainly in the article: this measures whether a tool captures a
known agent-shaped workload, not whether it captures YOUR agent. A tool that handles our
scripted nesting correctly could still mishandle an exotic framework integration.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

ROOT = Path(os.environ.get("BENCHCLAW_ROOT", Path(__file__).resolve().parents[1]))
"""Repository root. Override with BENCHCLAW_ROOT when running from a copy."""
OUT = ROOT / "methodology/bc039-workload-v0.1.0.json"

SUITE_VERSION = "bc039-v0.1.0"

# Span kinds we count separately. The addendum forbids averaging these into one figure:
# dropping token counts and dropping tool spans are different failures.
LLM = "llm"
TOOL = "tool"
RETRIEVAL = "retrieval"

# Fixed synthetic corpus for the retrieval steps. No network, no vector store — retrieval
# here is a deterministic dict lookup that we wrap in a retrieval span. We are measuring
# whether the span is captured, not whether the retrieval is any good.
CORPUS = {
    "policy-refund": "Refunds are issued within 18 days of delivery, exclusive of the delivery date.",
    "policy-shipping": "Standard shipping is 5 business days; expedited is 2.",
    "policy-warranty": "Hardware carries a 24-month limited warranty from the invoice date.",
    "sku-BCL-204": "Trace Beacon, 7 in stock, reorder point 10.",
    "sku-BCL-311": "Span Relay, 42 in stock, reorder point 15.",
}

# Deterministic tool implementations. Same contract as adapters/shared_tools.py: pure
# functions over a fixed fixture, no clock, no randomness.
TOOL_FIXTURES = {
    "inventory_lookup": {
        "BCL-204": {"sku": "BCL-204", "available": 7, "reorder_point": 10},
        "BCL-311": {"sku": "BCL-311", "available": 42, "reorder_point": 15},
    },
    "shipment_status": {
        "TRK-8891": {"tracking_id": "TRK-8891", "days_in_transit": 9, "promised_days": 5},
    },
    "price_lookup": {
        "BCL-204": {"sku": "BCL-204", "unit_price": 129.0},
        "BCL-311": {"sku": "BCL-311", "unit_price": 64.5},
    },
}


def step(kind, name, *, parent, fails=False, detail=None):
    """One scripted step. `parent` is the index of the parent step, or None for a root child.

    Nesting is explicit because a flat trace is a captured-but-useless trace, and
    parent-child correctness is one of the primary outcomes.
    """
    return {
        "kind": kind,
        "name": name,
        "parent": parent,
        "fails": fails,
        "detail": detail or {},
    }


def scenario(scenario_id, prompt, steps, note):
    return {"id": scenario_id, "prompt": prompt, "steps": steps, "note": note}


# ---------------------------------------------------------------------------
# The six scenarios. Chosen to cover each signal type and each nesting shape once,
# plus the two error paths, rather than to look impressive.
# ---------------------------------------------------------------------------

SCENARIOS = [
    scenario(
        "single-call",
        "Reply with the single word: acknowledged.",
        [step(LLM, "chat.completion", parent=None)],
        "Floor case. One LLM span, no children. An arm that drops this is broken, not slow.",
    ),
    scenario(
        "tool-sequence",
        "Check stock for BCL-204, then look up its price, then state both.",
        [
            step(LLM, "chat.completion.plan", parent=None),
            step(TOOL, "inventory_lookup", parent=0, detail={"sku": "BCL-204"}),
            step(TOOL, "price_lookup", parent=0, detail={"sku": "BCL-204"}),
            step(LLM, "chat.completion.summarise", parent=None),
        ],
        "Two tool spans parented to the LLM span that requested them. The common shape.",
    ),
    scenario(
        "retrieval-augmented",
        "Using the retrieved policy text, state the refund window in days.",
        [
            step(RETRIEVAL, "corpus.fetch.policy", parent=None, detail={"key": "policy-refund"}),
            step(RETRIEVAL, "corpus.fetch.shipping", parent=None, detail={"key": "policy-shipping"}),
            step(LLM, "chat.completion.answer", parent=None),
            step(TOOL, "shipment_status", parent=2, detail={"tracking_id": "TRK-8891"}),
        ],
        "Retrieval spans are the signal most often missing from a default integration.",
    ),
    scenario(
        "nested-deep",
        "Summarise stock and price for BCL-311 in one sentence.",
        [
            step(LLM, "chat.completion.outer", parent=None),
            step(TOOL, "inventory_lookup", parent=0, detail={"sku": "BCL-311"}),
            step(RETRIEVAL, "corpus.fetch.sku", parent=1, detail={"key": "sku-BCL-311"}),
            step(TOOL, "price_lookup", parent=1, detail={"sku": "BCL-311"}),
            step(LLM, "chat.completion.inner", parent=2),
        ],
        "Depth 4. Tests whether nesting survives, not merely whether spans arrive.",
    ),
    scenario(
        "tool-error",
        "Look up stock for the unknown SKU BCL-999 and report the failure honestly.",
        [
            step(LLM, "chat.completion.plan", parent=None),
            step(TOOL, "inventory_lookup", parent=0, fails=True, detail={"sku": "BCL-999"}),
            step(TOOL, "price_lookup", parent=0, detail={"sku": "BCL-204"}),
            step(LLM, "chat.completion.recover", parent=None),
        ],
        "One injected tool exception. Error records are a counted signal, not a nuisance.",
    ),
    scenario(
        "llm-error",
        "Reply with the single word: recovered.",
        [
            step(LLM, "chat.completion.doomed", parent=None, fails=True),
            step(LLM, "chat.completion.retry", parent=None),
        ],
        "An LLM span that raises. Some integrations record only successful calls.",
    ),
]


def ground_truth(scenarios):
    """Exact per-scenario and total span counts. This is the denominator we own."""
    per_scenario = {}
    totals = {LLM: 0, TOOL: 0, RETRIEVAL: 0, "errors": 0, "spans": 0, "nested_edges": 0}
    for sc in scenarios:
        counts = {LLM: 0, TOOL: 0, RETRIEVAL: 0, "errors": 0, "nested_edges": 0}
        for st in sc["steps"]:
            counts[st["kind"]] += 1
            if st["fails"]:
                counts["errors"] += 1
            if st["parent"] is not None:
                counts["nested_edges"] += 1
        counts["spans"] = len(sc["steps"])
        counts["max_depth"] = _max_depth(sc["steps"])
        per_scenario[sc["id"]] = counts
        for key in totals:
            totals[key] += counts[key]
    return {"per_scenario": per_scenario, "per_run_totals": totals}


def _max_depth(steps):
    def depth(i):
        parent = steps[i]["parent"]
        return 1 if parent is None else 1 + depth(parent)

    return max(depth(i) for i in range(len(steps)))


def build():
    suite = {
        "suite_version": SUITE_VERSION,
        "generated_by": "operations/bc039_workload.py",
        "deterministic": True,
        "control_flow": "scripted",
        "control_flow_rationale": (
            "The model is called at fixed points but never decides how many spans are "
            "emitted. Without this the capture denominator would vary per run and a drop "
            "would be indistinguishable from the model simply doing less work."
        ),
        "corpus": CORPUS,
        "tool_fixtures": TOOL_FIXTURES,
        "scenarios": SCENARIOS,
        "ground_truth": ground_truth(SCENARIOS),
    }
    return suite


def main():
    suite = build()
    payload = json.dumps(suite, indent=2, sort_keys=False) + "\n"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(payload)
    digest = hashlib.sha256(payload.encode()).hexdigest()
    totals = suite["ground_truth"]["per_run_totals"]
    print(json.dumps({"out": str(OUT), "sha256": digest, "per_run_totals": totals}, indent=2))


if __name__ == "__main__":
    main()
