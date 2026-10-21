#!/usr/bin/env python3
"""Read Cursor's published pricing and documentation, print one JSON document.

Standard library only, no account, nothing is billed, no model is called. Reads:
  - https://cursor.com/pricing                                      (current plans)
  - https://cursor.com/docs/models-and-pricing.md                   (plan table, annual prices, third-party model rates, Cursor Token Rate)
  - https://cursor.com/docs/account/pricing/legacy-cursor-plans.md  (the plans Cursor sold before The X Subscription)
  - https://cursor.com/help/the-x-subscription/overview.md
  - https://platform.claude.com/docs/en/about-claude/pricing.md     (Anthropic's own API rates, to check Cursor's "API list price")
  - https://code.claude.com/docs/en/costs.md                        (one worked agent session, token counts only, reused for arithmetic)
  - seven pages that rank for "cursor pricing" or are cited by Google's AI Overview, fetched only to see what they mention
  - google-ai-overview-cursor-pricing-2026-10-21.md                 (Google's AI Overview, saved next to this script)

Before computing anything of our own it compares every Claude row in Cursor's third-party table with Anthropic's published rate for the same
model. Rows that differ are reported as data. Pages are read live, so a later run can differ if the vendors change them; --as-of is a label.

Usage: python3 check_cursor_pricing.py [--as-of 2026-10-21] > out.json
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


def money(s):
    return D(s.replace(",", "").lstrip("$"))


def f(x, places="0.01"):
    return float(D(x).quantize(D(places), rounding=ROUND_HALF_UP))


pricing_html = must("https://cursor.com/pricing")
models_md = must("https://cursor.com/docs/models-and-pricing.md")
legacy_md = must("https://cursor.com/docs/account/pricing/legacy-cursor-plans.md")
xsub_md = must("https://cursor.com/help/the-x-subscription/overview.md")
api_md = must("https://platform.claude.com/docs/en/about-claude/pricing.md")
costs_md = must("https://code.claude.com/docs/en/costs.md")
aio = open(os.path.join(HERE, "google-ai-overview-cursor-pricing-2026-10-21.md"), encoding="utf-8").read()
page = re.sub(r"\s+", " ", " ".join(text_lines(pricing_html)))
models_flat = re.sub(r"\s+", " ", models_md)
legacy_flat = re.sub(r"\s+", " ", legacy_md)
xsub_flat = re.sub(r"\s+", " ", xsub_md)

# ---- 1. Current plans on the pricing page ---------------------------------------------------------------
def rx(pattern):
    m = re.search(pattern, page)
    return m.group(1) if m else None


live_plans = {
    "Free": rx(r"Free (\$0) /month"),
    "Plus": rx(r"Plus (\$\d+) /month"),
    "Premium": rx(r"Premium Most popular (\$\d+) /month"),
    "Super": rx(r"Super (\$\d+) /month"),
    "Ultra": rx(r"Ultra (\$\d+) /month"),
}
live_multipliers = {"Premium": rx(r"Everything in Plus, and: (\d+x) more usage compared to Plus"),
                    "Super": rx(r"Everything in Premium, and: (\d+x) more usage compared to Plus"),
                    "Ultra": rx(r"Everything in Super, and: (\d+x) more usage compared to Plus")}
page_phrases = {
    "only_grok_models_on_plus": "Only Grok models are available on this plan" in page,
    "third_party_billed_separately": "3rd party models are available in Cursor, billed separately by usage" in page,
    "third_party_at_api_list_price": "Third-party models remain available in Cursor at API list price" in page,
    "allowance_refreshes_weekly": "Your allowance refreshes weekly" in page,
    "premium_includes_third_party_models_allowance": "do not include an allowance for third-party models" in page,
    "sold_through_x_subscription_corp": "X Subscription Corp" in page,
    "mentions_pro_plus_or_teams_standard": any(s in page for s in ("Pro+", "$60/month", "$40/user")),
}

# ---- 2. Plan table and annual prices in the documentation ------------------------------------------------
plan_rows = {}
for name in ("Free", "Plus", "Premium", "Super", "Ultra", "Teams", "Enterprise"):
    m = re.search(r"^\|\s*\*\*" + name + r"\*\*\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|", models_md, re.M)
    plan_rows[name] = {"price": m.group(1), "included_usage": m.group(2), "third_party": m.group(3)} if m else None
annual = {k: v for k, v in re.findall(r"(\$[\d,]+)/yr for (\w+)", models_md) and [(b, a) for a, b in re.findall(r"(\$[\d,]+)/yr for (\w+)", models_md)]}
annual_prices = {name: money(price) for name, price in annual.items()}
monthly_prices = {n: money(p) for n, p in (("Plus", "$8"), ("Premium", "$30"), ("Super", "$100"), ("Ultra", "$200"))}
annual_saving = {n: {"monthly_billing_12_months_usd": int(monthly_prices[n] * 12), "annual_billing_usd": int(annual_prices[n]),
                     "saving_percent": f((monthly_prices[n] * 12 - annual_prices[n]) / (monthly_prices[n] * 12) * 100, "0.1")}
                 for n in monthly_prices if n in annual_prices}
docs_say = {
    "cursor_sold_as_part_of_the_x_subscription": "Cursor is sold as part of [The X Subscription]" in models_md,
    "weekly_pool_shared_across_grok_and_cursor": "shared across Grok and Cursor" in models_flat,
    "legacy_plans_named": "Pro, Pro+, Ultra, Start, or a Teams Standard or Premium seat? Those are [legacy Cursor plans]" in models_md,
    "third_party_not_included_billed_at_api_list_price_from_prepaid_credit": "Third-party models aren't included; on Premium and above you can use them at API list price, paid from prepaid credit" in models_flat,
    "teams_seat_tiers": "Each member gets a Premium, Super, or Ultra seat at the same price and with the same weekly usage as the matching individual plan" in models_flat,
    "cursor_token_rate_per_million": "Cursor Token Rate of $0.25 per million tokens" in models_flat,
    "token_rate_applies_to_input_output_cached": "It applies to input tokens, output tokens, and cached tokens" in models_flat,
    "token_rate_not_for_individual_plans": "Individual plans don't pay it" in models_flat,
    "unify_switch_permanent": "Switching to The X Subscription is optional and permanent" in legacy_flat,
    "new_customers_start_on_x_subscription": "New customers" in legacy_flat and "start on The X Subscription" in legacy_flat,
    "legacy_plans_keep_working": "They keep working as they are" in legacy_flat,
    "x_sub_switch_cannot_be_undone": "It can't be undone" in xsub_flat,
    "plus_has_no_auto_cloud_agents_or_third_party_models": "No Auto, Cloud Agents, Automations, Bugbot, Origin, third-party models, or your own API keys" in models_flat,
    "cost_mode_draws_from_weekly_pool": "Cost mode (classic Auto) bills as a Cursor-model request and draws from your weekly pool whatever model serves it" in models_flat,
    "individual_plans_have_cost_mode_only": "Individual plans have Cost mode only" in models_flat,
    "free_plan_agent_and_chat_limited_usage": "Agent and Chat with limited usage" in models_flat,
    "token_rate_excludes_claude_haiku_5_5": "These models are excluded from the Cursor Token Rate: - Claude Haiku 5.5" in models_flat,
    "monthly_additional_usage_limit_exists": "A **monthly additional usage limit** caps how much paid additional usage you can consume each month" in models_flat,
    "legacy_comparison_advice": "Compare both before you switch" in legacy_flat,
    "each_paid_plan_includes_at_least_twice_legacy_cursor_model_usage": "includes at least twice as much coding usage with Cursor models as the legacy plan it replaces" in legacy_flat,
}
acq = must("https://cursor.com/blog/joining-spacex")
acq_flat = re.sub(r"\s+", " ", " ".join(text_lines(acq)))
acquisition = {"url": "https://cursor.com/blog/joining-spacex", "dated_aug_14_2026": "Aug 14, 2026" in acq_flat,
               "says_officially_acquired_by_spacex": "Cursor has officially been acquired by SpaceX" in acq_flat,
               "says_started_in_april_with_spacexai_partnership": "started in April, when we announced our partnership with SpaceXAI" in acq_flat}

# ---- 3. Legacy plans and what they map to --------------------------------------------------------------------
legacy = {}
for name in ("Hobby", "Pro", "Pro+", "Ultra", "Teams Standard", "Teams Premium"):
    m = re.search(r"^\|\s*\*\*" + re.escape(name) + r"\*\*\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|", legacy_md, re.M)
    legacy[name] = {"price": m.group(1), "comparable_plan": m.group(2)} if m else None
changes = []
for old, new, oldp, newp in (("Pro", "Premium", 20, 30), ("Pro+", "Super", 60, 100), ("Ultra", "Ultra", 200, 200),
                             ("Teams Standard", "Teams Premium seat", 40, 30), ("Teams Premium", "Teams Super seat", 120, 100)):
    changes.append({"legacy": old, "comparable_current": new, "legacy_usd": oldp, "current_usd": newp,
                    "change_percent": f(D(newp - oldp) / D(oldp) * 100, "0.1")})
pool_per_dollar = {n: {"price_usd": int(monthly_prices[n]), "multiple_of_plus_pool": m,
                       "usd_per_plus_sized_pool": f(monthly_prices[n] / D(m))}
                   for n, m in (("Plus", 1), ("Premium", 4), ("Super", 15), ("Ultra", 50))}

# ---- 4. Cursor's "API list price" against Anthropic's published rates -----------------------------------------------
def anthropic_row(name):
    """First table row whose model cell equals `name` once any parenthetical note is removed (so 'Claude Fable 5' never matches 'Claude Fable 5.1')."""
    for line in api_md.splitlines():
        if not line.startswith("| Claude "):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if re.sub(r"\s*\(.*$", "", cells[0]).strip() != name:
            continue
        nums = [money(re.search(r"\$([0-9.,]+)", c).group(0)) for c in cells[1:6]]
        return {"input": nums[0], "cache_write": nums[1], "cache_read": nums[3], "output": nums[4]}
    return None


def to_anthropic_name(cursor_name):
    m = re.match(r"Claude (\d(?:\.\d)?) (Opus|Sonnet|Haiku)$", cursor_name)
    if m:
        return "Claude %s %s" % (m.group(2), m.group(1))
    return cursor_name


tp_start = models_md.index("### Model pricing")
claude_compare, unmatched = [], []
for line in models_md[tp_start:].splitlines():
    if not line.startswith("| [Claude "):
        continue
    cells = [c.strip() for c in line.strip("|").split("|")]
    name = re.match(r"\[([^\]]+)\]", cells[0]).group(1)
    if "1M" in name or "fast mode" in name:
        unmatched.append({"cursor_name": name, "reason": "variant with its own multiplier, not compared"})
        continue
    a = anthropic_row(to_anthropic_name(name))
    if not a:
        unmatched.append({"cursor_name": name, "reason": "no Anthropic row found by name"})
        continue
    c = {"input": money(cells[2]), "cache_write": money(cells[3]), "cache_read": money(cells[4]), "output": money(cells[5])}
    claude_compare.append({"cursor_name": name, "anthropic_name": to_anthropic_name(name),
                           "cursor": {k: float(v) for k, v in c.items()}, "anthropic": {k: float(v) for k, v in a.items()},
                           "identical": all(c[k] == a[k] for k in c)})
list_price_summary = {"claude_rows_compared": len(claude_compare), "identical": sum(1 for r in claude_compare if r["identical"]),
                      "different": [r for r in claude_compare if not r["identical"]], "not_compared": unmatched}

# ---- 5. The same worked session through Cursor, with and without the Cursor Token Rate ----------------------------------
m = re.search(r"claude-sonnet-4-6:\s+([0-9.]+)k input, ([0-9.]+)k output, ([0-9.]+)k cache read, ([0-9.]+)k cache write", costs_md)
tok = {k: D(v) * 1000 for k, v in zip(("input", "output", "cache_read", "cache_write"), m.groups())}
TOKEN_RATE = D("0.25")
sonnet55 = next(r for r in claude_compare if r["cursor_name"] == "Claude Sonnet 5.5")["cursor"]
opus55 = next(r for r in claude_compare if r["cursor_name"] == "Claude Opus 5.5")["cursor"]


def session(rate):
    return sum(tok[k] * D(str(rate[k])) / D(10 ** 6) for k in tok)


def with_rate(counted):
    return TOKEN_RATE * sum(tok[k] for k in counted) / D(10 ** 6)


all_four = ("input", "output", "cache_read", "cache_write")
without_cache_write = ("input", "output", "cache_read")
teams = {}
for label, rate in (("Claude Sonnet 5.5", sonnet55), ("Claude Opus 5.5", opus55)):
    base = session(rate)
    a, b = with_rate(all_four), with_rate(without_cache_write)
    teams[label] = {"individual_plan_usd": f(base, "0.0001"),
                    "teams_all_four_token_types_counted_usd": f(base + a, "0.0001"), "teams_extra_percent_all_four": f(a / base * 100, "0.1"),
                    "teams_cache_write_not_counted_usd": f(base + b, "0.0001"), "teams_extra_percent_without_cache_write": f(b / base * 100, "0.1")}
session_tokens = {k: int(v) for k, v in tok.items()}
session_tokens["cache_read_share_percent"] = f(tok["cache_read"] / sum(tok.values()) * 100, "0.1")

# ---- 6. Google's AI Overview against the live pages --------------------------------------------------------------------------
aio_claims = {
    "overview_lists_pro_20": "**Pro:** $20/month" in aio,
    "overview_lists_pro_plus_60": "$60/month" in aio,
    "overview_lists_ultra_200": "$200/month" in aio,
    "overview_lists_teams_40_per_user": "$40 per user/month" in aio,
    "overview_lists_hobby_free": "**Hobby (Free):**" in aio,
    "overview_says_pro_includes_unlimited_auto_mode": "Includes unlimited Auto mode" in aio,
    "overview_says_pro_16_annual": "$16/month if billed annually" in aio,
    "overview_says_third_party_credits_included": "provides a matching budget of usage credits for third-party frontier models" in aio,
    "overview_mentions_x_subscription": "X Subscription" in aio,
    "overview_mentions_grok": "Grok" in aio,
    "overview_mentions_plus_premium_or_super": [n for n in ("Plus", "Premium", "Super") if re.search(r"\b" + n + r"\b", aio)],
    "overview_mentions_spacex": "SpaceX" in aio,
    "live_pricing_page_lists_pro_or_pro_plus": page_phrases["mentions_pro_plus_or_teams_standard"],
    "legacy_page_lists_pro_20_pro_plus_60_ultra_200_teams_40": [legacy[k]["price"] if legacy[k] else None for k in ("Pro", "Pro+", "Ultra", "Teams Standard")],
}

# ---- 7. What seven pages mention ------------------------------------------------------------------------------------------------
PAGES = ["https://fadamakis.com/understanding-cursor-pricing-2ce7a6fd7930", "https://www.nxcode.io/resources/news/cursor-ai-pricing-plans-guide-2026",
         "https://skywork.ai/blog/vibecoding/cursor-2-0-pricing", "https://medium.com/@laurentkubaski/cursor-ai-pricing-explained-bf7444746ffe",
         "https://www.jetadmin.io/blog/cursor-pricing-explained-plans-credit-system-and-real-costs-in-2026/",
         "https://amnic.com/blogs/cursor-pricing", "https://www.superblocks.com/blog/cursor-enterprise"]
pages = []
for u in PAGES:
    st, body = get(u)
    t = re.sub(r"\s+", " ", " ".join(text_lines(body))) if body else ""
    pages.append({"url": u, "status": st, "chars": len(t),
                  "mentions": {"X Subscription": "X Subscription" in t, "Grok": "Grok" in t, "SpaceX": "SpaceX" in t, "Pro+": "Pro+" in t,
                               "$60": "$60" in t, "Premium $30": bool(re.search(r"Premium[^.]{0,40}\$30", t)), "Super $100": bool(re.search(r"Super[^.]{0,40}\$100", t))}})

json.dump({"as_of": AS_OF, "sources": ["https://cursor.com/pricing", "https://cursor.com/docs/models-and-pricing.md",
                                       "https://cursor.com/docs/account/pricing/legacy-cursor-plans.md",
                                       "https://cursor.com/help/the-x-subscription/overview.md", "https://cursor.com/blog/joining-spacex",
                                       "https://platform.claude.com/docs/en/about-claude/pricing.md", "https://code.claude.com/docs/en/costs.md"],
           "live_plans": live_plans, "live_multipliers_of_plus": live_multipliers, "pricing_page_phrases": page_phrases,
           "docs_plan_table": plan_rows, "docs_annual_prices_usd": {k: int(v) for k, v in annual_prices.items()}, "annual_saving": annual_saving,
           "docs_statements_found": docs_say, "acquisition_notice": acquisition, "legacy_plans": legacy, "legacy_to_current_price_change": changes,
           "weekly_pool_price_per_plus_sized_pool": pool_per_dollar, "cursor_list_price_vs_anthropic": claude_compare,
           "cursor_list_price_summary": list_price_summary, "worked_session_tokens": session_tokens, "worked_session_through_cursor_usd": teams,
           "ai_overview_vs_live_pages": aio_claims, "other_pages": pages},
          sys.stdout, indent=2, sort_keys=True)
sys.stdout.write("\n")
