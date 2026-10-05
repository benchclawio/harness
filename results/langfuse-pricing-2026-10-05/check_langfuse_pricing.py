#!/usr/bin/env python3
"""Read Langfuse's published pricing and docs, print one JSON document.

Standard library only, no API key, no account, nothing is billed. Reads four Langfuse pages
(published as Markdown by appending .md) plus LangSmith's pricing page for the comparison
rates. Before computing anything it reproduces the five worked examples Langfuse publishes on
its pricing page; if any differ the script exits non-zero.
"""
import html
import json
import re
import sys
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (benchclaw pricing check)"}


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return r.read().decode("utf-8", "replace")


pricing = get("https://langfuse.com/pricing.md")
units_doc = get("https://langfuse.com/docs/administration/billable-units.md")
selfhost = get("https://langfuse.com/pricing-self-host.md")
scaling = get("https://langfuse.com/self-hosting/configuration/scaling.md")
langsmith_html = get("https://www.langchain.com/pricing")

# ---- Cloud plans -----------------------------------------------------------------------
def plan(name):
    m = re.search(r"### %s[^\n]*\n(.*?)(?=\n### |\n## )" % re.escape(name), pricing, re.S)
    return m.group(0) if m else ""


def table_row(label):
    m = re.search(r"\|\s*%s\s*\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|" % re.escape(label), pricing)
    return [c.strip() for c in m.groups()] if m else [None] * 4


plans = {}
access, users, included = table_row("Access to historical data"), table_row("Users"), table_row("[Included usage](/docs/administration/billable-units)")
for i, name in enumerate(("Hobby", "Core", "Pro", "Enterprise")):
    head = re.search(r"### (%s[^\n]*)" % name, pricing)
    plans[name] = {"heading": head.group(1) if head else None,
                   "included_units": included[i], "data_access": access[i], "users": users[i]}
teams_addon = re.search(r"Teams Add-on\*\* \(\$([0-9,]+)/month\)", pricing)

tiers = [(m.group(1).strip(), float(m.group(2))) for m in
         re.finditer(r"\| ([0-9]+[kM]?\+? ?(?:--)? ?[0-9]*[kM]? units) +\| \$([0-9.]+) / 100k units", pricing)]
# Tier boundaries in units, then rate per 100k units.
TIERS = [(1_000_000, 8.00), (10_000_000, 7.00), (50_000_000, 6.50), (None, 6.00)]
INCLUDED = 100_000
BASE = {"Core": 29.0, "Pro": 199.0, "Pro+Teams": 499.0, "Enterprise": 2499.0}


def graduated(units):
    billable = max(0, units - INCLUDED)
    cost, lower = 0.0, INCLUDED
    for upper, rate in TIERS:
        top = units if upper is None else min(units, upper)
        if top > lower:
            cost += (top - lower) / 100_000 * rate
        lower = upper if upper is not None else lower
        if upper is None or units <= upper:
            break
    return cost


def cloud(plan_name, units):
    return round(BASE[plan_name] + graduated(units), 2)


# ---- Self-check: Langfuse's own five worked examples ------------------------------------
published = [float(x.replace(",", "")) for x in re.findall(r"\*\*Total: \$([0-9,.]+)/month\*\*", pricing)]
computed = [cloud("Core", 200_000), cloud("Core", 1_000_000), cloud("Pro", 5_000_000),
            cloud("Pro+Teams", 25_000_000), cloud("Enterprise", 100_000_000)]
selfcheck = {"published_examples_usd": published, "computed_usd": computed, "match": published == computed}
if not selfcheck["match"]:
    json.dump({"selfcheck": selfcheck}, sys.stdout, indent=2)
    sys.exit(1)

# ---- Billable units ---------------------------------------------------------------------
nums = lambda p: int(re.search(p, units_doc).group(1).replace(",", ""))
units_info = {
    "formula_present": "`Units` = `Count of Traces` + `Count of Observations` + `Count of Scores`" in units_doc,
    "doc_example_traces": nums(r"`([0-9,]+) Traces`"),
    "doc_example_observations": nums(r"`([0-9,]+) Observations`"),
    "doc_example_scores": nums(r"`([0-9,]+) Scores`"),
    "doc_example_units": nums(r"= `([0-9,]+) units / month`"),
    "langfuse_features_create_units": "created by Langfuse features such as LLM-as-a-Judge, Annotation Queues, or experiments" in units_doc,
}
units_info["units_per_trace_in_doc_example"] = round(
    units_info["doc_example_units"] / units_info["doc_example_traces"], 2)

# ---- Self-hosting -----------------------------------------------------------------------
rows = [l for l in selfhost.splitlines() if l.startswith("|") and l.count("|") >= 4]
strip = lambda s: re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s).strip()
oss_missing_enterprise_yes, oss_has = [], []
for l in rows:
    cells = [strip(c) for c in l.strip("|").split("|")]
    if len(cells) >= 3 and cells[1] == "--" and cells[2] == "Yes":
        oss_missing_enterprise_yes.append(cells[0])
    if len(cells) >= 3 and cells[1] == "Yes" and re.search(r"SSO|Organization-level RBAC", cells[0]):
        oss_has.append(cells[0])
infra = []
for l in scaling.splitlines():
    m = re.match(r"\| \[([^\]]+)\]\([^)]*\)\s*\| ([0-9]+) CPU, ([0-9.]+) GiB Memory", l)
    if m:
        infra.append({"service": m.group(1), "cpu": int(m.group(2)), "memory_gib": float(m.group(3))})
selfhost_info = {
    "mit_license_stated": "MIT License" in selfhost,
    "enterprise_bundled_with_clickhouse_plan": "Langfuse pricing is additive to your ClickHouse commercial plan" in selfhost,
    "oss_missing_but_enterprise_has": oss_missing_enterprise_yes,
    "oss_includes": oss_has,
    "minimum_infra": infra,
    "minimum_total_cpu": sum(i["cpu"] for i in infra),
    "minimum_total_memory_gib": sum(i["memory_gib"] for i in infra),
    "compose_is_single_vm_without_ha_or_backups": True,
}

# ---- LangSmith comparison rates (same page and tooltip as the LangSmith pricing article) --
ls_rate = float(re.search(r'data-tippy-content="([0-9.]+) LSU/base trace', langsmith_html).group(1))
ls_seat = float(re.search(r"seatPrice:([0-9.]+)", langsmith_html).group(1))
ls_included = int(re.search(r"tracesFreeIncluded:([0-9]+)", langsmith_html).group(1))
ls_lsu = float(re.search(r"lsuPrice:([0-9.]+)", langsmith_html).group(1))


def langsmith_plus(seats, traces):
    return round(seats * ls_seat + max(0, traces - ls_included) * ls_rate * ls_lsu, 2)


# ---- Example workloads ------------------------------------------------------------------
UPT = (1, 7, 20)
cloud_grid = []
for traces in (5_000, 10_000, 50_000, 100_000, 500_000, 1_000_000):
    for upt in UPT:
        units = traces * upt
        cloud_grid.append({"traces": traces, "units_per_trace": upt, "units": units,
                           "core_usd": cloud("Core", units), "pro_usd": cloud("Pro", units)})
comparison = []
for seats, traces, upt in ((1, 100_000, 7), (5, 100_000, 7), (5, 100_000, 20), (10, 500_000, 7)):
    comparison.append({"seats": seats, "traces": traces, "units_per_trace": upt,
                       "langsmith_plus_usd": langsmith_plus(seats, traces),
                       "langfuse_core_usd": cloud("Core", traces * upt)})
breakeven = {}
for seats, traces in ((1, 100_000), (5, 100_000)):
    target = langsmith_plus(seats, traces)
    upt = next((u for u in range(1, 1000) if cloud("Core", traces * u) >= target), None)
    breakeven[f"{seats}_seat_{traces}_traces"] = {"langsmith_plus_usd": target,
                                                 "first_units_per_trace_where_langfuse_core_costs_at_least_as_much": upt}

json.dump({
    "sources": ["https://langfuse.com/pricing.md", "https://langfuse.com/docs/administration/billable-units.md",
                "https://langfuse.com/pricing-self-host.md", "https://langfuse.com/self-hosting/configuration/scaling.md",
                "https://www.langchain.com/pricing"],
    "selfcheck_langfuse_published_examples": selfcheck,
    "cloud_plans": plans, "teams_addon_usd": int(teams_addon.group(1).replace(",", "")) if teams_addon else None,
    "graduated_tiers_parsed": tiers, "base_fees_usd": BASE, "included_units": INCLUDED,
    "billable_units": units_info, "self_hosting": selfhost_info,
    "langsmith_rates_used": {"seat_usd": ls_seat, "included_traces": ls_included,
                             "lsu_per_extra_trace": ls_rate, "usd_per_lsu": ls_lsu},
    "cloud_grid": cloud_grid, "comparison": comparison, "breakeven": breakeven,
}, sys.stdout, indent=2)
print()
