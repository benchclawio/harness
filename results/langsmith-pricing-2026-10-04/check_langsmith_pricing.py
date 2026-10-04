#!/usr/bin/env python3
"""Read LangSmith's published pricing and docs, print one JSON document.

Standard library only, no API key, no account, nothing is billed. It reads three public
pages (the pricing page, and two docs pages) plus the agentsapis.com pricing explainer,
then does the arithmetic for a few example workloads from the extracted rates.
"""
import html
import json
import re
import sys
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (benchclaw pricing check)"}


def get(url, accept=None):
    headers = dict(UA)
    if accept:
        headers["Accept"] = accept
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def text_of(raw):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw)))


def num(pattern, source, cast=float):
    m = re.search(pattern, source)
    return cast(m.group(1)) if m else None


pricing_html = get("https://www.langchain.com/pricing")
pricing_txt = text_of(pricing_html)
usage_md = get("https://docs.langchain.com/langsmith/usage-and-billing", "text/markdown")
billing_md = get("https://docs.langchain.com/langsmith/billing", "text/markdown")
third_party = text_of(get("https://agentsapis.com/langsmith-pricing/"))

lsu_per_base = num(r"data-tippy-content=\"([0-9.]+) LSU/base trace", pricing_html)
lsu_per_ext_upgrade = num(r"([0-9.]+) LSU/extended trace upgrade", pricing_html)
lsu_usd = num(r"1 LSU = \$([0-9.]+)", pricing_txt)
seat = num(r"\$([0-9]+) / seat per month then pay as you go Sign up", pricing_txt)
calc = {
    "traceLsuPerTrace": num(r"traceLsuPerTrace:([0-9.]+)", pricing_html),
    "seatPrice": num(r"seatPrice:([0-9.]+)", pricing_html),
    "tracesFreeIncluded": num(r"tracesFreeIncluded:([0-9.]+)", pricing_html, int),
    "lsuPrice": num(r"lsuPrice:([0-9.]+)", pricing_html),
}

page = {
    "developer_price": "$0 / seat per month" in pricing_txt,
    "developer_included_base_traces": 1000 * num(r"Up to ([0-9]+)k base traces / mo, then pay-as-you-go Community support", pricing_txt, int),
    "plus_seat_usd": seat,
    "plus_included_base_traces": 1000 * num(r"Up to ([0-9]+)k base traces / mo, then pay-as-you-go Access to Deployment", pricing_txt, int),
    "enterprise_custom_pricing": "Custom pricing" in pricing_txt,
    "enterprise_self_hosted_or_hybrid": "Self-hosted and hybrid deployment options" in pricing_txt,
    "lsu_usd": lsu_usd,
    "lsu_per_base_trace": lsu_per_base,
    "lsu_per_extended_upgrade": lsu_per_ext_upgrade,
    "base_retention_days": num(r"Base traces have a shorter retention period of ([0-9]+) days", pricing_txt, int),
    "extended_retention_days": num(r"Extended traces have a longer retention period of ([0-9]+) days", pricing_txt, int),
    "startup_credits_up_to_usd": num(r"Get up to \$([0-9,]+) in credits", pricing_txt.replace(",", ""), int),
    "calculator_constants": calc,
}

docs = {
    "usage_doc_retention_row": re.findall(r"\*\*Retention Period\*\* \| ([0-9]+) days \| ([0-9]+) days", usage_md),
    "usage_doc_sep_14_2026_notice": bool(re.search(r"Starting September 14, 2026, the maximum long-lived trace retention period for SaaS customers is changing to 180 days", usage_md)),
    "billing_doc_personal_org_cap": num(r"Personal organizations are limited to ([0-9,]+) traces per month until a credit card is added", billing_md.replace(",", ""), int),
    "billing_doc_plus_initial_traces": num(r"Team organizations are given an initial ([0-9,]+) traces per month", billing_md.replace(",", ""), int),
    "usage_doc_auto_upgrade_default_on": "Retention extension is enabled by default for new online evaluators and automation rules" in usage_md,
}

usd_base = (lsu_per_base or 0) * (lsu_usd or 0)
usd_upg = (lsu_per_ext_upgrade or 0) * (lsu_usd or 0)
derived = {
    "usd_per_1000_base_traces": round(usd_base * 1000, 4),
    "usd_per_1000_extended_upgrades": round(usd_upg * 1000, 4),
    "usd_per_1000_extended_total": round((usd_base + usd_upg) * 1000, 4),
}


def bill(plan, seats, traces, extended_share=0.0):
    included = 5000 if plan == "developer" else 10000
    seat_cost = 0 if plan == "developer" else seats * (seat or 0)
    billable = max(0, traces - included)
    # Assumption: the extended-retention upgrade fee applies to billable traces only.
    # The page does not say how included traces are treated.
    usage = billable * usd_base + billable * extended_share * usd_upg
    return {"plan": plan, "seats": seats, "traces": traces, "extended_share": extended_share,
            "seat_cost_usd": round(seat_cost, 2), "usage_cost_usd": round(usage, 2),
            "total_usd": round(seat_cost + usage, 2)}


scenarios = [
    bill("developer", 1, 5000),
    bill("developer", 1, 50000),
    bill("plus", 1, 10000),
    bill("plus", 3, 50000),
    bill("plus", 5, 100000),
    bill("plus", 5, 100000, 1.0),
    bill("plus", 10, 500000),
]

claims = {
    "agentsapis_base_per_1k": num(r"Base: \$([0-9.]+)/1k", third_party),
    "agentsapis_extended_per_1k": num(r"Extended: \$([0-9.]+)/1k", third_party),
    "agentsapis_upgrade_per_1k": num(r"Upgrade: \$([0-9.]+)/1k", third_party),
    "agentsapis_extended_retention_days": num(r"Extended retention: ([0-9]+) days", third_party, int),
}

json.dump({"sources": ["https://www.langchain.com/pricing",
                        "https://docs.langchain.com/langsmith/usage-and-billing",
                        "https://docs.langchain.com/langsmith/billing",
                        "https://agentsapis.com/langsmith-pricing/"],
           "pricing_page": page, "docs": docs, "derived": derived,
           "example_workloads": scenarios, "third_party_claims": claims},
          sys.stdout, indent=2)
print()
