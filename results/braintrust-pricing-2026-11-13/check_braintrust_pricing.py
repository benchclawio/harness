#!/usr/bin/env python3
"""Read Braintrust's public pricing page and do arithmetic on its published rates, print one JSON document.

Standard library only, no account, nothing billed, no Braintrust API called, no model called. Reads:
  - https://www.braintrust.dev/pricing : the visible plan table (Starter, Pro, Enterprise), the overage rates for processed data and scores,
    the retention line, the usage-calculator example, and the page's FAQ answers (embedded as JSON-LD)
  - google-ai-overview-braintrust-pricing-2026-11-13.md, saved next to this script, to check what the Overview says and leaves out

The arithmetic covers platform fee, processed data and scores only. Model credits (token rates are on a separate detailed page we did not read) and
retention beyond the plan's included days are excluded. All results are arithmetic on published prices, not observed bills. We assume the on-demand
overage rates apply on both plans, because the FAQ says Starter can "enable on-demand usage".

Usage: python3 check_braintrust_pricing.py > out.json
"""
import html
import json
import os
import re
import sys
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
HERE = os.path.dirname(os.path.abspath(__file__))


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}), timeout=40).read().decode("utf-8", "replace")


def text_of(page):
    page = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", "", page)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page))).strip()


raw = get("https://www.braintrust.dev/pricing")
text = text_of(raw)


def num(s):
    return float(s.replace(",", ""))


m = re.search(r"Starter For everyone \$(\d+) / month \$(\d+) credits \+ tok rates (\d+) GB processed data \+ \$(\d+(?:\.\d+)?)/GB (\d+)k scores \+ \$(\d+(?:\.\d+)?)/1k (\d+)-day retention", text)
starter = {"platform_fee": num(m.group(1)), "credits": num(m.group(2)), "included_gb": num(m.group(3)), "gb_rate": num(m.group(4)),
           "included_scores": num(m.group(5)) * 1000, "scores_rate_per_1k": num(m.group(6)), "retention_days": int(m.group(7))}
m = re.search(r"Pro For AI native teams \$(\d+) / month \$(\d+) credits \+ tok rates (\d+) GB processed data \+ \$(\d+(?:\.\d+)?)/GB (\d+)k scores \+ \$(\d+(?:\.\d+)?)/1k (\d+)-day retention \+ \$(\d+(?:\.\d+)?)/GB/mo", text)
pro = {"platform_fee": num(m.group(1)), "credits": num(m.group(2)), "included_gb": num(m.group(3)), "gb_rate": num(m.group(4)),
       "included_scores": num(m.group(5)) * 1000, "scores_rate_per_1k": num(m.group(6)), "retention_days": int(m.group(7)), "extra_retention_per_gb_month": num(m.group(8))}
page_facts = {
    "starter": starter, "pro": pro,
    "enterprise_custom_pricing": "Custom pricing" in text,
    "unlimited_users_all_plans": len(re.findall(r"Users Unlimited Unlimited Unlimited", text)) == 1,
    "pro_extended_retention_line": find if (find := re.search(r"Up to (\d+)-day data retention, billed at \$([\d.]+) per GB per month after the included (\d+)-day period", text)) else None,
    "startup_line": (re.search(r"(6.12 months free for qualifying startups)", text) or [None, None])[1],
    "no_credit_card_for_starter": "No credit card required" in text,
    "model_token_rates_on_this_page": bool(re.search(r"\$\d+(?:\.\d+)? ?/ ?(?:M|1M)Tok|per million tokens", text)),
}
if page_facts["pro_extended_retention_line"]:
    g = page_facts["pro_extended_retention_line"]
    page_facts["pro_extended_retention_line"] = {"up_to_days": int(g.group(1)), "per_gb_month": float(g.group(2)), "after_included_days": int(g.group(3))}

calc = re.search(r"([\d,]+) ?Tokens per month (\d+)% ?Scoring percentage", text)
calc_out = re.search(r"Storage \( ?([\d.]+) GB\) .*? Scores \( ?([\d,]+) ?\) .*? Estimated monthly total \$([\d.]+) \$([\d.]+) Custom", text)
calculator_example = {"tokens_per_month": int(num(calc.group(1))), "scoring_percentage": int(calc.group(2)), "storage_gb": float(calc_out.group(1)),
                      "scores": int(num(calc_out.group(2))), "estimated_starter_total": float(calc_out.group(3)), "estimated_pro_total": float(calc_out.group(4))}

faq = {}
for q, a in re.findall(r'"name":"([^"]+)","acceptedAnswer":\{"@type":"Answer","text":"((?:[^"\\]|\\.)*)"', raw):
    faq[html.unescape(q)] = html.unescape(json.loads('"' + a + '"'))
faq_facts = {
    "processed_data_is_ingested_not_stored": "Processed data refers to data ingested when you send data to Braintrust, not retained storage" in faq.get("What does processed data mean?", ""),
    "deleting_does_not_lower_processed_data": "deleting data does not lower processed data" in faq.get("What does processed data mean?", ""),
    "monthly_total_is_calendar_month": "calendar month" in faq.get("What does processed data mean?", ""),
    "each_recorded_score_counts_one": "the total number of scores counted towards your monthly usage increases by one" in faq.get("What are scores?", ""),
    "starter_needs_on_demand_to_exceed": "enable on-demand usage" in faq.get("How does billing work?", ""),
    "pro_charged_prorated_on_signup": "prorated amount of the monthly $249 platform fee" in faq.get("How does billing work?", ""),
    "usage_charges_billed_after_month": "On the 1st of the following month, you'll be charged the full $249 fee plus any additional usage-based charges" in faq.get("How does billing work?", ""),
    "pro_described_as_up_to_5_people": "small teams of up to 5 people" in faq.get("Which plan is right for me?", ""),
    "startup_condition": (re.search(r"have raised at least (\$[\d,K]+) in funding", faq.get("Do you offer discounts for startups?", "")) or [None, None])[1],
    "startup_must_be_new_customer": "must be a new Braintrust customer" in faq.get("Do you offer discounts for startups?", ""),
}


def cost(plan, gb, scores):
    data = max(0.0, gb - plan["included_gb"]) * plan["gb_rate"]
    sc = max(0.0, scores - plan["included_scores"]) / 1000 * plan["scores_rate_per_1k"]
    return {"platform": plan["platform_fee"], "data_overage": round(data, 2), "scores_overage": round(sc, 2), "total": round(plan["platform_fee"] + data + sc, 2)}


WORKLOADS = [("Solo prototype", 0.5, 5000), ("Small app", 2, 20000), ("The page's own calculator example", calculator_example["storage_gb"], calculator_example["scores"]),
             ("Pro's included allowance", 5, 50000), ("Heavy evals", 10, 100000), ("Production agent", 50, 500000), ("Large", 200, 2000000)]
workloads = []
for name, gb, sc in WORKLOADS:
    s, p = cost(starter, gb, sc), cost(pro, gb, sc)
    workloads.append({"name": name, "processed_gb": gb, "scores": sc, "starter": s, "pro": p, "cheaper": "Starter" if s["total"] < p["total"] else ("Pro" if p["total"] < s["total"] else "equal")})


def breakeven(axis):
    """Smallest value on one axis (the other held at Starter's included allowance) where Pro costs no more than Starter."""
    lo, step = (1.0 if axis == "gb" else 10000.0), (0.01 if axis == "gb" else 10.0)
    v = lo
    for _ in range(10_000_000):
        gb, sc = (v, starter["included_scores"]) if axis == "gb" else (starter["included_gb"], v)
        if cost(pro, gb, sc)["total"] <= cost(starter, gb, sc)["total"]:
            return round(v, 2)
        v += step
    return None


breakevens = {"processed_gb_with_scores_held_at_10k": breakeven("gb"), "scores_with_data_held_at_1gb": breakeven("scores")}

aio = open(os.path.join(HERE, "google-ai-overview-braintrust-pricing-2026-11-13.md"), encoding="utf-8").read()
overview = aio.split("## Sources cited by the overview")[0]
claims = {
    "overview_starter_matches_page": "$0 / month" in overview and "$10 in monthly model credits" in overview and "1 GB of processed data" in overview and "10,000 scores" in overview and "14-day" in overview,
    "overview_pro_matches_page": "$249 / month" in overview and "$100 in monthly model credits" in overview and "5 GB" in overview and "50,000 scores" in overview and "30-day" in overview,
    "overview_gives_gb_overage_rates": "+$4 per GB" in overview and "+$3 per GB" in overview,
    "overview_gives_score_overage_rates": "$2.50 per 1,000" in overview and "$1.50 per 1,000" in overview,
    "overview_gives_retention_extension_rate": "$0.50 per GB per month" in overview,
    "overview_says_processed_data_means_ingested": bool(re.search(r"ingest", overview, re.I)),
    "overview_says_deleting_does_not_reduce_usage": bool(re.search(r"deleting", overview, re.I)),
    "overview_mentions_startup_program": bool(re.search(r"startup", overview, re.I)),
    "overview_mentions_on_demand_needed_for_starter": bool(re.search(r"on-demand usage|enable on-demand", overview, re.I)),
    "overview_mentions_billing_in_arrears_or_proration": bool(re.search(r"prorat|following month", overview, re.I)),
    "overview_gives_a_worked_workload": bool(re.search(r"for example|e\.g\.|a team that", overview, re.I)),
    "overview_has_token_rates": bool(re.search(r"\$\d+(?:\.\d+)? ?/ ?M?Tok|per million", overview, re.I)),
}

json.dump({"source_url": "https://www.braintrust.dev/pricing", "page_facts": page_facts, "calculator_example": calculator_example, "faq_facts": faq_facts,
           "faq_questions_found": sorted(faq), "workloads": workloads, "breakevens": breakevens, "claims_checked": claims}, sys.stdout, indent=2, sort_keys=True)
sys.stdout.write("\n")
