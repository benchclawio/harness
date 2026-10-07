#!/usr/bin/env python3
"""Read OpenRouter's and its alternatives' published fees, the Stripe announcement, and repository status.

Standard library only, no API key, no account, nothing is billed. Reads public pricing pages and docs, the
OpenRouter and Stripe announcement pages, and GitHub repository and release data. It then does the fee arithmetic for
three monthly spend levels. This is published pricing and metadata, not a measurement of routing quality or latency.
"""
import datetime
import html
import json
import os
import re
import sys
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (benchclaw gateway check)", "Accept": "application/json, text/markdown, text/html"}
TODAY = datetime.date.today()


def get(url, text=False):
    headers = dict(UA)
    token = os.environ.get("GITHUB_TOKEN")  # optional: only lifts GitHub's 60-requests-an-hour limit
    if token and url.startswith("https://api.github.com/"):
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=40) as r:
        body = r.read().decode("utf-8", "replace")
    return body if text else json.loads(body)


def plain(page):
    t = re.sub(r"<(script|style).*?</\1>", " ", page, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", t)))


def num(p, s, cast=float, g=1):
    m = re.search(p, s)
    return cast(m.group(g).replace(",", "")) if m else None


# ---- OpenRouter ---------------------------------------------------------------------------------
pricing = get("https://openrouter.ai/pricing.md", text=True)
faq = get("https://openrouter.ai/docs/faq.md", text=True)
post = get("https://openrouter.ai/blog/announcements/openrouter-is-joining-stripe/", text=True)
stripe_post = get("https://stripe.com/newsroom/news/stripe-agrees-to-acquire-openrouter", text=True)
post_txt = plain(post)
row = re.search(r"\| Platform fees \| N/A \| ([\d.]+)% \| ([\d.]+)% \|", pricing)
byok = re.search(r"\| BYOK Limits[^|]*\| No \| \$([\d,]+) of list price inference / month with no fees, (\d+)% fee after", pricing)
openrouter = {
    "standard_platform_fee_pct": float(row.group(1)) if row else None,
    "business_platform_fee_pct": float(row.group(2)) if row else None,
    "byok_free_list_price_usd_per_month": int(byok.group(1).replace(",", "")) if byok else None,
    "byok_fee_pct_after": int(byok.group(2)) if byok else None,
    "inference_billed_at_provider_list_price": "billed at each provider's list price" in pricing,
    "credit_fee_stripe": ("5.5% ($0.80 minimum)" in faq),
    "free_plan_requests_per_day": num(r"\| Rate limits \| (\d+) requests/day", pricing, int),
    "joining_stripe_post_date": (re.search(r"OpenRouter\s*\W+\s*(\d+/\d+/\d{4})", post_txt) or [None, None])[1],
    "post_says_expected_close": "We expect to close in the coming weeks" in post_txt,
    "post_says_transaction_subject_to_closing_conditions": "subject to customary closing conditions" in post_txt,
    "stripe_post_published": (re.search(r'datePublished":"(\d{4}-\d{2}-\d{2})', stripe_post) or [None, None])[1],
    "stripe_post_url": "https://stripe.com/newsroom/news/stripe-agrees-to-acquire-openrouter",
}

# ---- Alternatives' pricing pages ----------------------------------------------------------------
cf = plain(get("https://developers.cloudflare.com/ai-gateway/reference/pricing/", text=True))
vc = plain(get("https://vercel.com/docs/ai-gateway/pricing", text=True))
pk = plain(get("https://portkey.ai/pricing", text=True))
hc = plain(get("https://www.helicone.ai/pricing", text=True))
rq = plain(get("https://www.requesty.ai/pricing", text=True))
alternatives = {
    "cloudflare_ai_gateway": {
        "core_features_free": "core features available today are offered for free" in cf,
        "credit_example_usd": ([int(x) for x in re.search(r"a \$(\d+) credit purchase will result in a \$(\d+) charge", cf).groups()] if re.search(r"a \$(\d+) credit purchase will result in a \$(\d+) charge", cf) else None),
        "inference_passthrough_no_markup": "passed through with no markup" in cf,
        "free_plan_log_limit": num(r"Workers Free \| ([\d,]+) logs total", cf, int)},
    "vercel_ai_gateway": {
        "no_markup_no_platform_fee_on_tokens": "charges no markup and no platform fee on tokens" in vc,
        "customer_pays_payment_processing_fees": "responsible for any payment processing fees" in vc,
        "byok_no_markup_on_paid_tier": "With BYOK, there is no markup or fee from AI Gateway" in vc},
    "portkey": {
        "free_recorded_logs_per_month": (num(r"Free Forever.*?(\d+)k recorded logs per month", pk, int) or 0) * 1000 or None,
        "production_usd_per_month": num(r"\$(\d+)/month Great for teams ready to deploy", pk, int),
        "overage_usd_per_extra_100k_requests": num(r"\+\$(\d+) overages per additional 100k requests", pk, int),
        "free_tier_not_for_production_per_its_page": "Not suitable for production workloads" in pk},
    "helicone": {
        "hobby_free_requests": num(r"([\d,]+) free requests", hc, int),
        "pro_usd_per_month": num(r"Pro POPULAR \$(\d+) per month", hc, int),
        "team_usd_per_month": num(r"Team BEST VALUE \$(\d+) per month", hc, int)},
    "requesty": {
        "markup_pct_on_spend": num(r"plus (\d+)%", rq, int),
        "example": "A model that costs $10 per 1M tokens from OpenAI costs $10.50 through Requesty" in rq},
}

# ---- Repositories --------------------------------------------------------------------------------
repos = []
for name, repo in [("LiteLLM", "BerriAI/litellm"), ("Portkey gateway", "Portkey-AI/gateway"),
                   ("Helicone", "Helicone/helicone"), ("TensorZero", "tensorzero/tensorzero")]:
    g = get(f"https://api.github.com/repos/{repo}")
    rels = [r for r in get(f"https://api.github.com/repos/{repo}/releases?per_page=100") if not r["prerelease"] and not r["draft"]]
    dates = [r["published_at"][:10] for r in rels]
    repos.append({"name": name, "repo": repo, "license": (g.get("license") or {}).get("spdx_id"), "archived": g["archived"],
                  "pushed_at": g["pushed_at"][:10], "latest_release": dates[0] if dates else None,
                  "days_since_latest_release": (TODAY - datetime.date.fromisoformat(dates[0])).days if dates else None,
                  "releases_last_90_days": sum(1 for d in dates if (TODAY - datetime.date.fromisoformat(d)).days <= 90)})

# ---- Fee arithmetic (assumes all spend goes through the gateway's own credits, ignores minimum charges) ----
spend = [1000, 10000, 50000]
fees = {}
for s in spend:
    byok_fee = max(0, s - (openrouter["byok_free_list_price_usd_per_month"] or 0)) * (openrouter["byok_fee_pct_after"] or 0) / 100
    fees[str(s)] = {
        "openrouter_standard_credits": round(s * (openrouter["standard_platform_fee_pct"] or 0) / 100, 2),
        "openrouter_business_credits": round(s * (openrouter["business_platform_fee_pct"] or 0) / 100, 2),
        "openrouter_byok": round(byok_fee, 2),
        "cloudflare_unified_billing_5pct": round(s * 0.05, 2),
        "requesty": round(s * (alternatives["requesty"]["markup_pct_on_spend"] or 0) / 100, 2),
        "vercel_platform_fee": 0.0,
    }

json.dump({"read_on": TODAY.isoformat(), "openrouter": openrouter, "alternatives": alternatives, "repositories": repos,
           "monthly_model_spend_usd_to_fee_usd": fees,
           "fee_arithmetic_assumptions": "All spend bought as the gateway's credits; fee shown is the platform or credit fee only, excluding payment processing and any minimum charge; Portkey and Helicone price by logs or requests, not by spend, so they are not in this table"},
          sys.stdout, indent=2)
print()
