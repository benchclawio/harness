#!/usr/bin/env python3
"""Build bc-038 corpus v0.2.0 from the preserved v0.1.0 pilot corpus.

The pilot exposed two corpus defects before publication:

1. `format_violation` relied on a restock rule absent from the evaluator input.
2. `wrong_tool_sequence` did not offer the lookup whose omission defined the defect.

This deterministic repair makes both facts observable and leaves every other case byte-for-
byte equivalent at the field level. The v0.1.0 corpus and results remain immutable evidence.
"""

from __future__ import annotations

import copy
import json
import sys
from collections import Counter
from pathlib import Path


UNIT_PRICE = {
    "BCL-204": 129.00,
    "BCL-311": 64.50,
    "BCL-450": 212.75,
    "BCL-512": 88.00,
    "BCL-677": 41.25,
    "BCL-703": 310.00,
}

REFUND_POLICY = (
    "Exclude the delivery date when counting elapsed full days. A refund is eligible "
    "only when fewer than 18 full days have elapsed."
)

RESTOCK_POLICY = (
    "When available stock is below the reorder point, replenish to twice the reorder "
    "point. Otherwise order zero units."
)


def replace_policy(case: dict, policy_name: str, text: str) -> None:
    for step in case["trajectory"]:
        if step["tool"] == "policy_lookup" and step["arguments"].get("policy") == policy_name:
            step["result"] = {"policy": policy_name, "text": text}
            return
    case["trajectory"].append(
        {
            "tool": "policy_lookup",
            "arguments": {"policy": policy_name},
            "result": {"policy": policy_name, "text": text},
        }
    )


def repair(source: dict) -> dict:
    corpus = copy.deepcopy(source)
    cases = corpus["cases"]
    by_id = {case["case_id"]: case for case in cases}

    for case in cases:
        source_task = case["source_task_id"]

        if source_task.startswith("arith-"):
            replace_policy(case, "refund", REFUND_POLICY)

        if source_task.startswith("fmt-"):
            replace_policy(case, "restock", RESTOCK_POLICY)

    # A valid sequence pair must hold the final answer fixed and vary the path. The wrong
    # member omits an offered price lookup; the correct member calls it. Both receive the
    # same task, tools, inventory result, output contract and final output.
    for wrong in [c for c in cases if c.get("defect_class") == "wrong_tool_sequence"]:
        correct = by_id[wrong["matched_with"]]
        sku = wrong["agent_output"]["sku"]
        quantity = wrong["agent_output"]["quantity"]
        unit_price = UNIT_PRICE[sku]
        output = {
            "sku": sku,
            "quantity": quantity,
            "total_usd": round(unit_price * quantity, 2),
            "unavailable": False,
        }
        prompt = (
            f"Compute the total order value for {quantity} units of {sku}. "
            "Use the provided tools and do not guess any required value."
        )
        tools = ["inventory_lookup", "price_lookup"]
        inventory_step = copy.deepcopy(wrong["trajectory"][0])
        price_step = {
            "tool": "price_lookup",
            "arguments": {"sku": sku},
            "result": {"sku": sku, "unit_price_usd": unit_price, "currency": "USD"},
        }

        wrong.update(
            {
                "prompt": prompt,
                "tools_offered": tools,
                "trajectory": [inventory_step],
                "agent_output": output,
                "reference_answer": output,
                "construction": (
                    "the true final answer is supplied, but the offered price_lookup was "
                    "not called; the missing tool step is the only defect"
                ),
            }
        )
        correct.update(
            {
                "prompt": prompt,
                "tools_offered": tools,
                "trajectory": [copy.deepcopy(inventory_step), price_step],
                "agent_output": copy.deepcopy(output),
                "reference_answer": copy.deepcopy(output),
                "origin": "constructed",
                "construction": (
                    "matched control for wrong_tool_sequence: identical final answer after "
                    "the offered price_lookup is called"
                ),
            }
        )

    wrong = [case for case in cases if case["label"] == "wrong"]
    correct = [case for case in cases if case["label"] == "correct"]
    wrong_classes = Counter(case["defect_class"] for case in wrong)

    corpus.update(
        {
            "corpus_version": "bc038-corpus-v0.2.0",
            "built": "2026-08-14",
            "governed_by": "methodology/bc038-corpus-spec-v0.2.0.md v0.2.0",
            "generated_by": "operations/bc038_repair_corpus.py",
            "repair_of": "bc038-corpus-v0.1.0",
            "pilot_status": (
                "v0.1.0 results are retained as an invalidated pilot and must not be used "
                "to rank evaluator arms"
            ),
            "counts": {
                "total": len(cases),
                "wrong": len(wrong),
                "correct": len(correct),
                "wrong_by_class": dict(sorted(wrong_classes.items())),
            },
            "origin_counts": {
                "wrong_induced": sum(case["origin"] == "induced" for case in wrong),
                "wrong_constructed": sum(case["origin"] == "constructed" for case in wrong),
                "correct_induced": sum(case["origin"] == "induced" for case in correct),
                "correct_constructed": sum(case["origin"] == "constructed" for case in correct),
            },
            "disclosure": (
                "All 35 pairs share a task, prompt, offered tools and output contract. For "
                "five output-defect classes the trajectory is also identical and only the "
                "final output changes. For wrong_tool_sequence the final output is identical "
                "and only the trajectory changes: the wrong member omits an offered "
                "price_lookup, while the correct member calls it. Of 35 wrong outputs, one "
                "is induced and 34 are constructed. Correct outputs are induced where a "
                "clean induction run exists and constructed otherwise. Corpus v0.2.0 repairs "
                "two defects found by the post-run v0.1.0 audit; v0.1.0 is not rankable."
            ),
        }
    )
    return corpus


def main() -> None:
    source_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2])
    source = json.loads(source_path.read_text())
    assert source["corpus_version"] == "bc038-corpus-v0.1.0"
    repaired = repair(source)
    out_path.write_text(json.dumps(repaired, indent=1) + "\n")
    print(json.dumps({key: value for key, value in repaired.items() if key != "cases"}, indent=2))


if __name__ == "__main__":
    main()
