#!/usr/bin/env python3
"""Read Anthropic's published Claude plan and API pricing and Claude Code's cost documentation, print one JSON document.

Standard library only, no API key, no account, nothing is billed, no model is called. Reads:
  - https://claude.com/pricing                                   (plans, seat prices, API rates, FAQ)
  - https://platform.claude.com/docs/en/about-claude/pricing.md  (API price table, all models)
  - https://code.claude.com/docs/en/costs.md                     (what Claude Code costs, with a worked session)
  - six pages that rank for "claude code pricing", fetched only to see which prices and models they mention
  - google-ai-overview-claude-code-pricing-2026-10-21.md         (Google's AI Overview, saved next to this script)

Before computing anything of our own it recomputes the worked session printed in Anthropic's cost documentation (Sonnet 4.6, $0.55)
from the documented token counts and the documented per-token rates, and exits non-zero if the figures disagree.

Pages are read live, so a later run can differ if Anthropic changes them. The date given with --as-of is a label, not a filter.

Usage: python3 check_claude_code_pricing.py [--as-of 2026-10-21] > out.json
"""
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
from decimal import Decimal as D, ROUND_HALF_UP

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
HERE = os.path.dirname(os.path.abspath(__file__))
AS_OF = sys.argv[sys.argv.index("--as-of") + 1] if "--as-of" in sys.argv else "2026-10-21"


def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=45) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return 0, ""


def must(url):
    st, body = get(url)
    if st != 200 or not body:
        sys.exit("abort: %s returned %s" % (url, st))
    return body


def text_lines(raw):
    t = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", "", raw)
    t = re.sub(r"<[^>]+>", "\n", t)
    return [l.strip() for l in html.unescape(t).splitlines() if l.strip()]


def usd(x):
    return float(D(x).quantize(D("0.0001"), rounding=ROUND_HALF_UP))


def cents(x):
    return float(D(x).quantize(D("0.01"), rounding=ROUND_HALF_UP))


page_html = must("https://claude.com/pricing")
api_md = must("https://platform.claude.com/docs/en/about-claude/pricing.md")
costs_md = must("https://code.claude.com/docs/en/costs.md").replace("\\$", "$")
aio = open(os.path.join(HERE, "google-ai-overview-claude-code-pricing-2026-10-21.md"), encoding="utf-8").read()
L = text_lines(page_html)
page_text = "\n".join(L)
flat = re.sub(r"\s+", " ", page_text)

# ---- 1. Plan prices on the pricing page -----------------------------------------------------------
data_plan = sorted({(m.group(1), m.group(2) or "", m.group(3).strip()) for m in
                    re.finditer(r'data-plan="([^"]+)"(?:\s+data-plan-field="([^"]+)")?[^>]*>([^<]*)<', page_html) if m.group(3).strip()})


def after(label, start=0, count=8):
    i = L.index(label, start)
    return L[i + 1:i + 1 + count]


team_at = L.index("For teams of 2 to 150")
team = {"audience": L[team_at],
        "standard_seat": after("Standard seat", team_at, 6),
        "premium_seat": after("Premium seat", team_at, 6)}
ent_at = L.index("For large businesses operating at scale")
enterprise = after("Seat price + usage at API rates", ent_at, 2)
pro_at = L.index("For everyday work")
max_at = L.index("For people who work with Claude all day")
individual = {"pro": L[pro_at + 1:pro_at + 6], "max": L[max_at + 1:max_at + 5]}

phrases = {
    "claude_code_included_in_all_paid_plans": "Claude Code is included in all paid plans" in flat,
    "shares_limits_with_chat": "shares the same usage limits as the rest of your plan" in flat,
    "rolling_five_hour_window": "reset on a rolling five-hour session window" in flat,
    "paid_plans_add_weekly_limits": "paid plans add weekly limits on top" in flat,
    "usage_credits_at_standard_api_rates": "turn on usage credits to keep working at standard API rates" in flat,
    "max_5x_or_20x_per_5_hour_session": "5x or 20x the usage of Pro per 5-hour session" in flat,
    "team_standard_more_than_pro": "Standard seats give more than Pro and Premium seats give 5x more than Standard" in flat,
    "enterprise_20_seat_minimum": "20 seat minimum" in flat,
    "enterprise_annual_only": "Enterprise plans are only available as annual subscriptions" in flat,
    "team_pooled_api_credits_500": "Up to $500 per month in pooled API credits" in flat,
    "max_api_credits_100_to_200": "$100 to $200/month in API credits to build on the Claude Platform" in flat,
    "pay_as_you_go_via_console": "switch to pay-as-you-go API credits through a Console account" in flat,
}
number_of_times_1_25x_appears = len(re.findall(r"1\.25\s*x", flat))

# ---- 2. API rates: pricing page against the documentation table ------------------------------------


def docs_row(name):
    m = re.search(r"^\|\s*" + re.escape(name) + r"\s*\|([^\n]*)$", api_md, re.M)
    cells = [c.strip() for c in m.group(1).split("|")]
    nums = [re.search(r"\$([0-9.]+)", c).group(1) for c in cells[:5]]
    return {"input": nums[0], "cache_write_5m": nums[1], "cache_write_1h": nums[2], "cache_read": nums[3], "output": nums[4]}


def page_block(name, start):
    i = L.index(name, start)
    seg = L[i:i + 24]
    out = {}
    for key, label in (("cache_read", "Read"), ("cache_write_5m", "Write"), ("input", "Input"), ("output", "Output")):
        j = seg.index(label)
        out[key] = seg[j + 1].lstrip("$")
    return out


latest_at = L.index("Latest models")
rates = {}
for name in ("Claude Fable 5.1", "Claude Opus 5.5", "Claude Sonnet 5.5", "Claude Sonnet 4.6", "Claude Haiku 5.5 (for prompts up to 100,000 tokens)"):
    rates[name] = {"docs": docs_row(name)}
for page_name, doc_name in (("Fable 5.1", "Claude Fable 5.1"), ("Opus 5.5", "Claude Opus 5.5"), ("Sonnet 5.5", "Claude Sonnet 5.5")):
    rates[doc_name]["pricing_page"] = page_block(page_name, latest_at)
    rates[doc_name]["page_matches_docs"] = all(rates[doc_name]["pricing_page"][k] == rates[doc_name]["docs"][k]
                                               for k in ("input", "output", "cache_read", "cache_write_5m"))

# ---- 3. The worked session in the cost documentation, recomputed -------------------------------------
m = re.search(r"Total cost:\s+\$([0-9.]+)\n.*?claude-sonnet-4-6:\s+([0-9.]+)k input, ([0-9.]+)k output, ([0-9.]+)k cache read, ([0-9.]+)k cache write", costs_md, re.S)
published_total, kin, kout, kcr, kcw = m.groups()
tok = {"input": D(kin) * 1000, "output": D(kout) * 1000, "cache_read": D(kcr) * 1000, "cache_write_5m": D(kcw) * 1000}


def session_cost(rate):
    return sum(tok[k] * D(rate[k]) / D(10 ** 6) for k in tok)


recomputed = session_cost(rates["Claude Sonnet 4.6"]["docs"])
selfcheck = {"published_total_usd": float(published_total), "recomputed_usd": cents(recomputed), "tokens": {k: int(v) for k, v in tok.items()},
             "matches": cents(recomputed) == float(published_total)}
if not selfcheck["matches"]:
    json.dump({"selfcheck": selfcheck}, sys.stdout, indent=2, sort_keys=True)
    sys.exit(1)

same_session_now = {n: {"usd": cents(session_cost(rates[n]["docs"])), "rates": rates[n]["docs"]}
                    for n in ("Claude Sonnet 5.5", "Claude Opus 5.5", "Claude Fable 5.1")}
total_tokens = sum(tok.values())
cache_read_share = float((tok["cache_read"] / total_tokens * 100).quantize(D("0.1")))

# ---- 4. What the cost documentation says about typical spend -------------------------------------------
costs_flat = re.sub(r"\s+", " ", costs_md)
spend_sentence = re.search(r"the average cost is around \$13 per developer per active day and \$150-250 per developer per month, with costs remaining below \$30 per active day for 90% of users", costs_flat)
spend = {"sentence_found": bool(spend_sentence), "per_active_day_avg_usd": 13, "per_month_range_usd": [150, 250], "p90_per_active_day_usd_below": 30,
         "charges_by_token": "Claude Code charges by API token consumption" in costs_flat,
         "subscribers_session_figure_not_billing": "Claude Max and Pro subscribers have usage included in their subscription" in costs_flat,
         "data_residency_multiplier_1_1": "1.1" in costs_flat}

# ---- 5. Our arithmetic on the published prices ------------------------------------------------------
def f_days(total, per_day):
    return float((D(total) / D(per_day)).quantize(D("0.1"), rounding=ROUND_HALF_UP))


plans = {"Pro": {"monthly": 20, "annual_per_month": 17, "annual_up_front": 200},
         "Team Standard seat": {"monthly": 25, "annual_per_month": 20},
         "Team Premium seat": {"monthly": 125, "annual_per_month": 100}}
for p, v in plans.items():
    yearly_monthly = v["monthly"] * 12
    yearly_annual = v.get("annual_up_front", v["annual_per_month"] * 12)
    v["twelve_months_monthly_billing"] = yearly_monthly
    v["twelve_months_annual_billing"] = yearly_annual
    v["annual_saving_percent"] = float((D(yearly_monthly - yearly_annual) / D(yearly_monthly) * 100).quantize(D("0.1")))
arith = {
    "plans": plans,
    "enterprise_minimum_seat_cost_per_year_usd": 20 * 20 * 12,
    "team_two_seat_minimum_per_month_standard_annual_usd": 2 * 20,
    "docs_average_per_active_day_times_20_days_usd": 13 * 20,
    "docs_range_per_month_usd": [150, 250],
    "active_days_per_month_implied_by_the_two_docs_figures": [f_days(150, 13), f_days(250, 13)],
    "pro_monthly_price_times_5_equals_max_5x_entry_price": 20 * 5 == 100,
    "max_5x_monthly_usd": 100,
    "premium_seat_vs_standard_seat_price_ratio": float(D(100) / D(20)),
}

# ---- 6. Google's AI Overview against the live pages -------------------------------------------------------
aio_claims = {
    "pro_17_annual_20_monthly": ("$17/mo billed annually" in aio and "$20/mo monthly" in aio) and any(t == "$17" for _, _, t in [(0, 0, x) for x in L]),
    "overview_states_max_5x_100_and_20x_200": "Max 5x ($100/mo" in aio and "Max 20x ($200/mo" in aio,
    "page_html_has_a_max_5x_price_attribute": any(p.startswith("max_5x") for p, _, _ in data_plan),
    "page_html_has_a_max_20x_price_attribute": any(p.startswith("max_20x") for p, _, _ in data_plan),
    "page_html_mentions_200_per_month_as_api_credits_only": "$200/month" in page_html and not any(p.startswith("max_20x") for p, _, _ in data_plan),
    "team_standard_20_annual_25_monthly": "Team Standard ($20/seat/mo annual or $25/mo monthly)" in aio,
    "team_premium_100_annual_125_monthly": "Team Premium ($100/seat/mo annual or $125/mo monthly)" in aio,
    "overview_says_team_standard_is_1_25x_pro": "1.25x Pro" in aio,
    "page_says_1_25x_anywhere": number_of_times_1_25x_appears > 0,
    "overview_says_team_premium_is_6_25x_pro": "6.25x Pro" in aio,
    "page_says_6_25x_anywhere": len(re.findall(r"6\.25\s*x", flat)) > 0,
    "overview_enterprise_20_per_seat_plus_usage": "Enterprise ($20/seat/mo billed annually + usage)" in aio,
    "overview_mentions_20_seat_minimum": "20 seat" in aio,
    "overview_mentions_max_api_credits": "API credits" in aio and "Max" in aio and "$100 to $200" in aio,
    "overview_mentions_team_pooled_credits": "pooled" in aio,
    "overview_mentions_weekly_limits": "weekly" in aio.lower(),
    "overview_mentions_five_hour_window": "5-hour" in aio or "five-hour" in aio.lower(),
    "overview_mentions_any_current_model_name": [n for n in ("Fable", "Opus 5.5", "Sonnet 5.5", "Haiku 5.5") if n in aio],
}

# ---- 7. What six ranking pages mention ------------------------------------------------------------------------
RANKERS = ["https://www.finout.io/blog/claude-pricing-in-2026-for-individuals-organizations-and-developers",
           "https://www.productcompass.pm/p/claude-code-pricing", "https://www.gosearch.ai/faqs/what-is-claude-enterprise-pricing-in-2026/",
           "https://blog.promptlayer.com/claude-ai-pricing-choosing-the-right-model/", "https://benchlm.ai/anthropic/api-pricing",
           "https://magai.co/claude-pricing/"]
ranking = []
for u in RANKERS:
    st, body = get(u)
    t = re.sub(r"\s+", " ", " ".join(text_lines(body))) if body else ""
    ranking.append({"url": u, "status": st, "chars": len(t),
                    "mentions": {n: (n in t) for n in ("Fable", "Opus 5.5", "Sonnet 5.5", "Haiku 5.5", "Opus 4.", "Sonnet 4.", "weekly limit", "$17")}})

json.dump({"as_of": AS_OF, "sources": ["https://claude.com/pricing", "https://platform.claude.com/docs/en/about-claude/pricing.md",
                                       "https://code.claude.com/docs/en/costs.md"],
           "plan_prices_on_page": {"individual": individual, "team": team, "enterprise": enterprise, "data_plan_attributes": [list(x) for x in data_plan]},
           "page_phrases_found": phrases, "api_rates_usd_per_million_tokens": rates, "selfcheck_docs_example": selfcheck,
           "same_session_at_current_rates": same_session_now, "session_cache_read_share_percent": cache_read_share,
           "docs_spend_statement": spend, "arithmetic": arith, "ai_overview_vs_live_page": aio_claims, "ranking_pages": ranking},
          sys.stdout, indent=2, sort_keys=True)
sys.stdout.write("\n")
