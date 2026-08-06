#!/usr/bin/env python3
"""Generate the frozen bc-025 capability pool and task suite.

Deterministic and offline. No model calls, no network, no randomness — running this
twice produces byte-identical output, so the suite SHA in the manifest is meaningful.

The pool is 20 capabilities because that is the scale at which the progressive-disclosure
claim is actually made; deferral of three tools saves nothing worth measuring. Every run in
every cell registers all 20. The arms differ only in whether those 20 are marked
`defer_loading`, so any token difference is attributable to disclosure and nothing else.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(os.environ.get("BENCHCLAW_ROOT", Path(__file__).resolve().parents[1]))
"""Repository root. Override with BENCHCLAW_ROOT when running from a copy."""
OUT = ROOT / "methodology/bc025-task-suite-v0.1.0.json"

SUITE_VERSION = "bc025-v0.1.0"


def capability(name, description, properties, required, fixture):
    return {
        "name": name,
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
        "fixture": fixture,
    }


STR = {"type": "string"}
NUM = {"type": "number"}


CAPABILITIES = [
    capability(
        "inventory_lookup",
        "Return the canonical synthetic inventory record for one exact SKU.",
        {"sku": STR}, ["sku"],
        {"BCL-204": {"sku": "BCL-204", "name": "Trace Beacon", "available": 7, "reorder_point": 10}},
    ),
    capability(
        "shipment_status",
        "Return the current synthetic status record for one exact tracking identifier.",
        {"tracking_id": STR}, ["tracking_id"],
        {"TRK-8891": {"tracking_id": "TRK-8891", "carrier": "Northline", "days_in_transit": 9, "promised_days": 5}},
    ),
    capability(
        "currency_convert",
        "Convert an amount between two currency codes using a fixed synthetic rate table.",
        {"amount": NUM, "from_currency": STR, "to_currency": STR},
        ["amount", "from_currency", "to_currency"],
        {"USD:EUR": 0.92, "EUR:USD": 1.087, "USD:GBP": 0.79, "GBP:USD": 1.266},
    ),
    capability(
        "defect_rate",
        "Return the recorded defect rate and control threshold for one production line.",
        {"line_id": STR}, ["line_id"],
        {"LINE-3": {"line_id": "LINE-3", "defect_rate_pct": 4.6, "threshold_pct": 3.0, "units_sampled": 500}},
    ),
    capability(
        "customer_record",
        "Return the synthetic account record for one exact customer identifier.",
        {"customer_id": STR}, ["customer_id"],
        {"CUS-1042": {"customer_id": "CUS-1042", "tier": "gold", "open_tickets": 2}},
    ),
    capability(
        "invoice_total",
        "Return the line-item total and currency for one exact invoice identifier.",
        {"invoice_id": STR}, ["invoice_id"],
        {"INV-7781": {"invoice_id": "INV-7781", "total": 4820.5, "currency": "USD"}},
    ),
    capability(
        "refund_eligibility",
        "Return the refund window and policy class for one exact order identifier.",
        {"order_id": STR}, ["order_id"],
        {"ORD-3312": {"order_id": "ORD-3312", "window_days": 30, "policy_class": "standard"}},
    ),
    capability(
        "warehouse_capacity",
        "Return used and total pallet capacity for one warehouse site code.",
        {"site_code": STR}, ["site_code"],
        {"WH-NORTH": {"site_code": "WH-NORTH", "pallets_used": 812, "pallets_total": 1000}},
    ),
    capability(
        "carrier_rate",
        "Return the quoted synthetic carrier rate for a lane and billable weight.",
        {"origin": STR, "destination": STR, "weight_kg": NUM},
        ["origin", "destination", "weight_kg"],
        {"LDN:BER": {"base": 42.0, "per_kg": 1.15}},
    ),
    capability(
        "tax_rate",
        "Return the applicable synthetic sales tax rate for one region code.",
        {"region_code": STR}, ["region_code"],
        {"EU-DE": {"region_code": "EU-DE", "rate_pct": 19.0}},
    ),
    capability(
        "sla_target",
        "Return the response and resolution SLA targets for one support tier.",
        {"tier": STR}, ["tier"],
        {"gold": {"tier": "gold", "response_hours": 2, "resolution_hours": 24}},
    ),
    capability(
        "return_window",
        "Return the permitted return window in days for one product class.",
        {"product_class": STR}, ["product_class"],
        {"electronics": {"product_class": "electronics", "window_days": 14}},
    ),
    capability(
        "supplier_lead_time",
        "Return quoted and historical lead times for one supplier identifier.",
        {"supplier_id": STR}, ["supplier_id"],
        {"SUP-55": {"supplier_id": "SUP-55", "quoted_days": 21, "historical_days": 27}},
    ),
    capability(
        "batch_expiry",
        "Return the manufacture and expiry dates for one production batch.",
        {"batch_id": STR}, ["batch_id"],
        {"BATCH-901": {"batch_id": "BATCH-901", "manufactured": "2026-01-10", "expires": "2027-01-10"}},
    ),
    capability(
        "temperature_log",
        "Return the last recorded reading and permitted range for one cold-chain sensor.",
        {"sensor_id": STR}, ["sensor_id"],
        {"SEN-12": {"sensor_id": "SEN-12", "last_celsius": 6.4, "max_celsius": 5.0}},
    ),
    capability(
        "staffing_roster",
        "Return scheduled and required headcount for one shift code.",
        {"shift_code": STR}, ["shift_code"],
        {"SH-NIGHT": {"shift_code": "SH-NIGHT", "scheduled": 11, "required": 14}},
    ),
    capability(
        "fuel_surcharge",
        "Return the current synthetic fuel surcharge percentage for one delivery zone.",
        {"zone": STR}, ["zone"],
        {"Z4": {"zone": "Z4", "surcharge_pct": 7.5}},
    ),
    capability(
        "packaging_spec",
        "Return carton dimensions and unit count for one packaged SKU.",
        {"sku": STR}, ["sku"],
        {"BCL-204": {"sku": "BCL-204", "units_per_carton": 12, "carton_kg": 8.4}},
    ),
    capability(
        "customs_code",
        "Return the tariff classification code and duty rate for one product class.",
        {"product_class": STR}, ["product_class"],
        {"electronics": {"product_class": "electronics", "hs_code": "8517.62", "duty_pct": 2.6}},
    ),
    capability(
        "insurance_premium",
        "Return the calculated synthetic insurance premium band for a declared value.",
        {"declared_value": NUM}, ["declared_value"],
        {"bands": [[0, 1000, 12.0], [1000, 10000, 48.0], [10000, 1000000, 210.0]]},
    ),
]


# Identical limits across every cell. They are set generously so that no limit binds in one
# arm and not the other: arm A needs 2 requests, arm B needs a search and a load first, and a
# ceiling that clipped only arm B would fabricate the very difference we are measuring.
LIMITS = {
    "model_requests": 6,
    "tool_calls": 4,
    "input_tokens": 40000,
    "output_tokens": 512,
    "total_tokens": 40512,
}


TASKS = [
    {
        "id": "inventory-reorder",
        "target_capability": "inventory_lookup",
        "prompt": (
            "Look up SKU BCL-204 using the inventory_lookup tool. Return ONLY a JSON object "
            "with exactly these keys: `sku` (string), `available` (integer), "
            "`reorder_required` (boolean, true when available is strictly less than "
            "reorder_point). Include no other keys or text."
        ),
        "reference_trace": [{"tool": "inventory_lookup", "arguments": {"sku": "BCL-204"}}],
        "expected_output": {"sku": "BCL-204", "available": 7, "reorder_required": True},
    },
    {
        "id": "shipment-delay",
        "target_capability": "shipment_status",
        "prompt": (
            "Look up tracking id TRK-8891 using the shipment_status tool. Return ONLY a JSON "
            "object with exactly these keys: `tracking_id` (string), `carrier` (string), "
            "`delayed` (boolean, true when days_in_transit is strictly greater than "
            "promised_days). Include no other keys or text."
        ),
        "reference_trace": [{"tool": "shipment_status", "arguments": {"tracking_id": "TRK-8891"}}],
        "expected_output": {"tracking_id": "TRK-8891", "carrier": "Northline", "delayed": True},
    },
    {
        "id": "currency-conversion",
        "target_capability": "currency_convert",
        "prompt": (
            "Convert 250 USD to EUR using the currency_convert tool. Return ONLY a JSON object "
            "with exactly these keys: `from_currency` (string), `to_currency` (string), "
            "`converted` (number, the tool's returned amount). Include no other keys or text."
        ),
        "reference_trace": [
            {
                "tool": "currency_convert",
                "arguments": {"amount": 250, "from_currency": "USD", "to_currency": "EUR"},
            }
        ],
        "expected_output": {"from_currency": "USD", "to_currency": "EUR", "converted": 230.0},
    },
    {
        "id": "defect-threshold",
        "target_capability": "defect_rate",
        "prompt": (
            "Look up production line LINE-3 using the defect_rate tool. Return ONLY a JSON "
            "object with exactly these keys: `line_id` (string), `defect_rate_pct` (number), "
            "`above_threshold` (boolean, true when defect_rate_pct is strictly greater than "
            "threshold_pct). Include no other keys or text."
        ),
        "reference_trace": [{"tool": "defect_rate", "arguments": {"line_id": "LINE-3"}}],
        "expected_output": {"line_id": "LINE-3", "defect_rate_pct": 4.6, "above_threshold": True},
    },
]


def build() -> dict:
    names = [c["name"] for c in CAPABILITIES]
    if len(set(names)) != len(names):
        raise SystemExit("capability names must be unique")
    for task in TASKS:
        if task["target_capability"] not in names:
            raise SystemExit(f"unknown target capability: {task['target_capability']}")

    return {
        "schema_version": 1,
        "suite_id": "bc025-deferred-disclosure",
        "suite_version": SUITE_VERSION,
        "publication_eligible": True,
        "purpose": (
            "Measure the real input-token, round-trip and correctness cost of progressive "
            "disclosure by running an identical task set with 20 capabilities always-on "
            "versus the same 20 behind deferred loading."
        ),
        "execution": {
            "model_id": "gpt-4o",
            "temperature": 0,
            "parallel_tool_calls": False,
            "framework_retries": 0,
            "provider_retries": 0,
        },
        "capability_count": len(CAPABILITIES),
        "limits": LIMITS,
        "output_policy": (
            "Exact match against expected_output after JSON parsing. Markdown code fences are "
            "stripped before parsing: gpt-4o wraps JSON in fences and that is a formatting "
            "artefact, not a correctness failure."
        ),
        "capabilities": CAPABILITIES,
        "tasks": TASKS,
    }


if __name__ == "__main__":
    OUT.write_text(json.dumps(build(), indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"written": str(OUT), "capabilities": len(CAPABILITIES), "tasks": len(TASKS)}))
