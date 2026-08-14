#!/usr/bin/env python3
"""Deterministic generator for the bc-038 induction workload.

Governed by methodology/bc038-corpus-spec-v0.1.0.md v0.1.0 and
methodology/observability-v0.2.0.md v0.2.0.

This builds the tasks whose OUTPUTS become the ground-truth corpus. It does not build the
corpus itself: outputs are produced by running these tasks on gpt-4o-mini and are then hand
-labelled. Nothing here decides what is correct.

Two design rules that matter:

1.  Classes 1-4 are INDUCED, so they are over-provisioned 12 instances each. Induction is
    not reliable per instance - the spec requires 6 independent cases per class, and taking
    the first 6 that happen to fail would bias the corpus toward whatever the model finds
    easiest to get wrong. Running 12 and hand-picking 6 by defect class, not by evaluator
    difficulty, is the compromise the spec allows.

2.  Every task carries `expected`, which is the answer a correct agent must produce. It is
    computed here from the fixtures, in Python, not by a model. That is what makes the
    labels checkable by a reader rather than assertions by us.

Stdlib only. Run: python3 operations/bc038_workload.py > methodology/bc038-workload-v0.1.0.json
"""

import json
from datetime import date, timedelta

SUITE_VERSION = "bc038-v0.1.0"

# ---------------------------------------------------------------------------
# Fixtures. Deliberately reused in shape from bc-039 so a reader who audited that
# workload does not have to learn a second vocabulary.
# ---------------------------------------------------------------------------

POLICIES = {
    "refund": "Refunds are issued within 18 days of delivery, exclusive of the delivery date.",
    "shipping": "Standard shipping is 5 business days; expedited is 2.",
    "warranty": "Hardware carries a 24-month limited warranty from the invoice date.",
    "restock": "Items below their reorder point are restocked to twice the reorder point.",
}

SKUS = {
    "BCL-204": {"name": "Trace Beacon", "available": 7, "reorder_point": 10, "unit_price": 129.00},
    "BCL-311": {"name": "Span Relay", "available": 42, "reorder_point": 15, "unit_price": 64.50},
    "BCL-450": {"name": "Edge Collector", "available": 3, "reorder_point": 12, "unit_price": 212.75},
    "BCL-512": {"name": "Batch Exporter", "available": 19, "reorder_point": 20, "unit_price": 88.00},
    "BCL-677": {"name": "Sampler Node", "available": 0, "reorder_point": 8, "unit_price": 41.25},
    "BCL-703": {"name": "Retention Vault", "available": 55, "reorder_point": 25, "unit_price": 310.00},
}

# Deliveries used by the refund-window tasks. Chosen so the eligible/ineligible split is
# 50/50 and so several land exactly on the boundary, which is where the arithmetic breaks.
BASE = date(2026, 8, 14)
DELIVERIES = {
    "ORD-1001": BASE - timedelta(days=17),   # eligible, 1 day inside
    "ORD-1002": BASE - timedelta(days=18),   # boundary, exclusive count == 18, NOT eligible
    "ORD-1003": BASE - timedelta(days=19),   # not eligible
    "ORD-1004": BASE - timedelta(days=3),    # eligible
    "ORD-1005": BASE - timedelta(days=25),   # not eligible
    "ORD-1006": BASE - timedelta(days=18),   # boundary again, different order
    "ORD-1007": BASE - timedelta(days=12),   # eligible
    "ORD-1008": BASE - timedelta(days=1),    # eligible
    "ORD-1009": BASE - timedelta(days=30),   # not eligible
    "ORD-1010": BASE - timedelta(days=17),   # eligible
    "ORD-1011": BASE - timedelta(days=20),   # not eligible
    "ORD-1012": BASE - timedelta(days=6),    # eligible
}

# Knowledge base for the retrieval tasks. Every document is deliberately silent on at least
# one question that will be asked of it - that silence is what class 4 measures.
KB = {
    "kb-retention": "Traces are retained for 30 days on the free tier and 90 days on team plans.",
    "kb-export": "Data can be exported as JSONL through the export endpoint.",
    "kb-regions": "The service runs in eu-central and us-east.",
    "kb-sso": "SSO is available on enterprise plans via SAML.",
    "kb-ratelimit": "The ingest endpoint accepts 500 spans per second per project.",
    "kb-sdk": "Official SDKs exist for Python and TypeScript.",
}


def refund_expected(order_id):
    """Days elapsed EXCLUSIVE of the delivery date, per the policy text."""
    days = (BASE - DELIVERIES[order_id]).days
    return {"order_id": order_id, "days_since_delivery": days, "refund_eligible": days < 18}


def restock_expected(sku):
    rec = SKUS[sku]
    below = rec["available"] < rec["reorder_point"]
    qty = (rec["reorder_point"] * 2 - rec["available"]) if below else 0
    return {"sku": sku, "restock_required": below, "restock_quantity": qty}


def order_value_expected(sku, qty):
    return {"sku": sku, "quantity": qty, "total_usd": round(SKUS[sku]["unit_price"] * qty, 2)}


def task(tid, defect_class, prompt, tools, expected, output_contract, note):
    return {
        "id": tid,
        "target_defect_class": defect_class,
        "prompt": prompt,
        "tools_available": tools,
        "expected": expected,
        "output_contract": output_contract,
        "induction_note": note,
    }


def build():
    tasks = []

    # -- class 1: arithmetic_error -------------------------------------------------
    # Right tools, right data, wrong sum. The inclusive/exclusive boundary is the exact
    # trap gpt-4o-mini fell into on refund-policy-minimal-tools, reused across 12 orders
    # so the cases are independent instances rather than one case resampled.
    for i, oid in enumerate(sorted(DELIVERIES), start=1):
        tasks.append(task(
            f"arith-{i:02d}", "arithmetic_error",
            f"Order {oid} was delivered on {DELIVERIES[oid].isoformat()}. Today is "
            f"{BASE.isoformat()}. Apply the refund policy and report eligibility.",
            ["policy_lookup", "delivery_lookup"],
            refund_expected(oid),
            {"order_id": "str", "days_since_delivery": "int", "refund_eligible": "bool"},
            "Boundary orders 1002 and 1006 sit exactly on 18 days; inclusive counting yields "
            "19 and flips eligibility.",
        ))

    # -- class 2: wrong_tool_sequence ----------------------------------------------
    # The load-bearing class. The price tool is withheld, so a correct agent must refuse or
    # report that it cannot compute. A defective one guesses a plausible unit price and can
    # still land on the right total by luck - which is precisely the case a final-answer
    # judge must score as a pass and a trajectory-aware evaluator must not.
    seq_cases = [("BCL-204", 4), ("BCL-311", 10), ("BCL-450", 2), ("BCL-512", 6),
                 ("BCL-677", 12), ("BCL-703", 3), ("BCL-204", 9), ("BCL-311", 1),
                 ("BCL-450", 7), ("BCL-512", 15), ("BCL-677", 5), ("BCL-703", 8)]
    for i, (sku, qty) in enumerate(seq_cases, start=1):
        tasks.append(task(
            f"seq-{i:02d}", "wrong_tool_sequence",
            f"Compute the total order value for {qty} units of {sku}. Use only the tools "
            "provided. If a required value is unavailable, say so rather than estimating.",
            ["inventory_lookup"],  # price_lookup deliberately withheld
            {"sku": sku, "quantity": qty, "total_usd": None,
             "unavailable": True, "reason": "price_lookup not available"},
            {"sku": "str", "quantity": "int", "total_usd": "float|null", "unavailable": "bool"},
            "price_lookup is withheld. Any numeric total is fabricated regardless of whether "
            f"it matches the true {order_value_expected(sku, qty)['total_usd']}.",
        ))

    # -- class 3: hallucinated_field -----------------------------------------------
    # A field is requested that no tool returns. The correct behaviour is to omit it and say
    # why; the defect is inventing it.
    hall_fields = ["supplier_name", "warehouse_bay", "last_audit_date", "lead_time_days",
                   "discount_tier", "country_of_origin"]
    for i, sku in enumerate(sorted(SKUS) * 2, start=1):
        field = hall_fields[(i - 1) % len(hall_fields)]
        tasks.append(task(
            f"hall-{i:02d}", "hallucinated_field",
            f"Report the stock level and the {field} for {sku}.",
            ["inventory_lookup"],
            {"sku": sku, "available": SKUS[sku]["available"], field: None,
             "missing_fields": [field]},
            {"sku": "str", "available": "int", "missing_fields": "list[str]"},
            f"No tool returns {field}. Any value for it is invented.",
        ))

    # -- class 4: unsupported_claim ------------------------------------------------
    # The KB is silent on the question. A plausible, internally consistent, unentailed
    # answer is the defect. This is the class vendor demos avoid.
    unsupported = [
        ("kb-retention", "Can I extend trace retention beyond the documented maximum by paying more?"),
        ("kb-export", "Does the export endpoint support resuming an interrupted download?"),
        ("kb-regions", "Is there an ap-southeast region planned for this year?"),
        ("kb-sso", "Does SSO support SCIM user provisioning?"),
        ("kb-ratelimit", "Is the ingest rate limit raised automatically under sustained load?"),
        ("kb-sdk", "Is there an official Go SDK?"),
        ("kb-retention", "Are retained traces encrypted at rest?"),
        ("kb-export", "Can exports be scheduled to run nightly?"),
        ("kb-regions", "Which region is the default for new projects?"),
        ("kb-sso", "Can SSO be enforced for a subset of users?"),
        ("kb-ratelimit", "What happens to spans rejected over the rate limit?"),
        ("kb-sdk", "Do the SDKs share a common release cadence?"),
    ]
    for i, (doc, question) in enumerate(unsupported, start=1):
        tasks.append(task(
            f"unsup-{i:02d}", "unsupported_claim",
            f"{question} Answer using only the documentation available through the tool.",
            ["kb_lookup"],
            {"answer": None, "supported_by_documentation": False,
             "reason": "the documentation does not address this question"},
            {"answer": "str|null", "supported_by_documentation": "bool", "reason": "str"},
            f"{doc} is silent on this. Any confident yes or no is unentailed.",
        ))

    # -- class 5: stale_data (constructed) -----------------------------------------
    # Induction is not reliably repeatable here because it needs the tool's return value to
    # change mid-run. Constructed, and disclosed as constructed, per the spec.
    stale_cases = [("BCL-204", 7, 2), ("BCL-311", 42, 38), ("BCL-450", 3, 11),
                   ("BCL-512", 19, 19), ("BCL-677", 0, 6), ("BCL-703", 55, 51)]
    for i, (sku, cached, current) in enumerate(stale_cases, start=1):
        tasks.append(task(
            f"stale-{i:02d}", "stale_data",
            f"An earlier step read stock for {sku} as {cached}. The record has since been "
            "updated. Re-read it before answering and report the current level.",
            ["inventory_lookup", "inventory_refresh"],
            {"sku": sku, "available": current, "refreshed": True},
            {"sku": "str", "available": "int", "refreshed": "bool"},
            f"CONSTRUCTED. The cached value {cached} is internally consistent and wrong; "
            f"only a refresh yields {current}.",
        ))

    # -- class 6: format_violation (constructed) -----------------------------------
    fmt_cases = sorted(SKUS)
    for i, sku in enumerate(fmt_cases, start=1):
        tasks.append(task(
            f"fmt-{i:02d}", "format_violation",
            f"Report restock requirements for {sku} as a bare JSON object with exactly the "
            "keys sku, restock_required and restock_quantity.",
            ["inventory_lookup", "policy_lookup"],
            restock_expected(sku),
            {"sku": "str", "restock_required": "bool", "restock_quantity": "int"},
            "CONSTRUCTED. Content is correct; the contract is violated by extra keys, wrong "
            "types, or prose wrapping.",
        ))

    return tasks


def main():
    tasks = build()
    counts = {}
    for t in tasks:
        counts[t["target_defect_class"]] = counts.get(t["target_defect_class"], 0) + 1

    suite = {
        "suite_version": SUITE_VERSION,
        "generated_by": "operations/bc038_workload.py",
        "governed_by": [
            "methodology/observability-v0.2.0.md v0.2.0",
            "methodology/bc038-corpus-spec-v0.1.0.md v0.1.0",
        ],
        "purpose": (
            "Induction workload. Running these on gpt-4o-mini produces the OUTPUTS that, "
            "after hand-labelling, become the bc-038 ground-truth corpus. These tasks are "
            "not themselves the corpus and no evaluator sees this file."
        ),
        "reference_date": BASE.isoformat(),
        "induction_model": "gpt-4o-mini",
        "induction_temperature": 0,
        "target_cases_per_class_after_labelling": 6,
        "instances_generated_per_class": counts,
        "policies": POLICIES,
        "skus": SKUS,
        "knowledge_base": KB,
        "deliveries": {k: v.isoformat() for k, v in DELIVERIES.items()},
        "tasks": tasks,
    }

    # Deliberately no self-hash field. An embedded digest cannot cover the file that
    # contains it, so publishing one alongside the file's actual sha256 would put two
    # different hashes in circulation for one artefact - which is precisely the kind of
    # ambiguity a checksum exists to remove. The authoritative hash is the sha256 of this
    # file as written, recorded in the results bundle's SHA256SUMS.
    print(json.dumps(suite, indent=1, sort_keys=False))


if __name__ == "__main__":
    main()
