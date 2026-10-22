#!/usr/bin/env python3
"""Read Anthropic's, OpenAI's and Google's published prompt-caching prices and rules and Amazon Bedrock's caching guide, print one JSON document.

Standard library only, no API key, no account, no model is called, nothing is billed. Reads:
  - https://platform.claude.com/docs/en/about-claude/pricing.md          (per-model input, cache-write, cache-hit and output rates)
  - https://platform.claude.com/docs/en/build-with-claude/prompt-caching.md
  - https://developers.openai.com/api/docs/pricing.md                    (input, cached-input and cache-write rates)
  - https://developers.openai.com/api/docs/guides/prompt-caching.md      (rules, minimums, retention, model differences)
  - https://ai.google.dev/gemini-api/docs/pricing.md.txt and /docs/caching (Gemini context-caching prices and minimums)
  - https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html
  - google-ai-overview-prompt-caching-2026-10-21.md, saved next to this script, to check its claims

Our arithmetic uses published prices only. It prices the input side of one reusable prefix and assumes every repeat request hits the cache, so
it is an upper bound on savings, not a measurement. Pages are read live; --as-of is a label, not a filter.

Usage: python3 check_prompt_caching.py [--as-of 2026-10-21] > out.json
"""
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
from decimal import Decimal as D, ROUND_HALF_UP

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36", "Accept-Language": "en-US,en;q=0.9"}
HERE = os.path.dirname(os.path.abspath(__file__))
AS_OF = sys.argv[sys.argv.index("--as-of") + 1] if "--as-of" in sys.argv else "2026-10-21"


def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
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


def flat(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s)))


def money(s):
    m = re.search(r"\$([0-9][0-9,]*\.?[0-9]*)", s or "")
    return D(m.group(1).replace(",", "")) if m else None


def r4(x):
    return float(D(x).quantize(D("0.0001"), rounding=ROUND_HALF_UP))


def r2(x):
    return float(D(x).quantize(D("0.01"), rounding=ROUND_HALF_UP))


api_md = must("https://platform.claude.com/docs/en/about-claude/pricing.md")
a_doc = must("https://platform.claude.com/docs/en/build-with-claude/prompt-caching.md")
o_price = must("https://developers.openai.com/api/docs/pricing.md")
o_guide = must("https://developers.openai.com/api/docs/guides/prompt-caching.md")
g_price = must("https://ai.google.dev/gemini-api/docs/pricing.md.txt")
g_doc = flat(must("https://ai.google.dev/gemini-api/docs/caching"))
bedrock = flat(must("https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html"))
aio = open(os.path.join(HERE, "google-ai-overview-prompt-caching-2026-10-21.md"), encoding="utf-8").read()


def plain(s):
    """Markdown to plain text for sentence checks: drop link targets and backticks."""
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)
    return flat(s.replace("`", ""))


a_doc_flat, o_guide_flat = plain(a_doc), plain(o_guide)

# ---- 1. Anthropic: every row of the API price table ---------------------------------------------------
anthropic = []
for line in api_md.splitlines():
    if not line.startswith("| Claude "):
        continue
    cells = [c.strip() for c in line.strip("|").split("|")]
    if len(cells) < 6:
        continue
    nums = [money(c) for c in cells[1:6]]
    if any(n is None for n in nums):
        continue
    name = re.sub(r"\s*\(.*$", "", cells[0]).strip()
    if "for prompts over" in cells[0]:
        name += " (over 100K)"
    inp, w5, w1, hit, out = nums
    anthropic.append({"model": name, "retired": "retired" in cells[0], "input": float(inp), "write_5m": float(w5), "write_1h": float(w1), "cache_hit": float(hit), "output": float(out),
                      "write_5m_x_input": r4(w5 / inp), "write_1h_x_input": r4(w1 / inp), "hit_x_input": r4(hit / inp)})
active = [r for r in anthropic if not r["retired"]]
anthropic_summary = {"rows": len(anthropic), "active_rows": len(active),
                     "write_5m_multiples": sorted({r["write_5m_x_input"] for r in active}), "write_1h_multiples": sorted({r["write_1h_x_input"] for r in active}),
                     "hit_multiples": sorted({r["hit_x_input"] for r in active}),
                     "lowest_hit_multiple": min(active, key=lambda r: r["hit_x_input"])["model"] + " " + str(min(r["hit_x_input"] for r in active))}
anthropic_rules = {
    "supported_on_all_active_models": "supported on all active Claude models" in a_doc_flat,
    "automatic_caching_exists": "automatic caching" in a_doc_flat.lower(),
    "explicit_breakpoints_5m_or_1h": "automatic caching or explicit breakpoints with 5-minute or 1-hour TTLs" in a_doc_flat,
    "default_ttl_5_minutes": "By default, automatic caching uses a 5-minute TTL" in a_doc_flat,
    "one_hour_at_additional_cost": "1-hour cache duration" in a_doc_flat and "additional cost" in a_doc_flat,
}

# ---- 2. OpenAI: pricing tables and the model-differences table -------------------------------------------
openai_new, openai_old = [], []
# Only the first "Standard pricing data" section: the page repeats the tables for other service tiers.
_start = o_price.index("### Standard pricing data")
_end = o_price.find("\n### ", _start + 10)
for line in o_price[_start:_end if _end > 0 else None].splitlines():
    if not line.startswith("| gpt-") and not line.startswith("| o"):
        continue
    cells = [c.strip() for c in line.strip("|").split("|")]
    vals = [money(c) for c in cells[1:]]
    if len(cells) == 11:
        inp, _out, cached, w30, w12 = vals[0], vals[1], vals[2], vals[3], vals[4]
        row = {"model": cells[0], "input": float(inp), "cached_input": float(cached) if cached else None, "write_30m": float(w30) if w30 else None, "write_12h": float(w12) if w12 else None}
        if cached:
            row["cached_x_input"] = r4(cached / inp)
        if w30:
            row["write_30m_x_input"] = r4(w30 / inp)
        if w12:
            row["write_12h_x_input"] = r4(w12 / inp)
        openai_new.append(row)
    elif len(cells) == 4:
        inp, cached = vals[0], vals[2]
        row = {"model": cells[0], "input": float(inp), "cached_input": float(cached) if cached else None}
        if cached:
            row["cached_x_input"] = r4(cached / inp)
        openai_old.append(row)
with_writes = [r for r in openai_new if r.get("write_30m")]
with_cache = [r for r in openai_new + openai_old if r.get("cached_x_input")]
openai_summary = {"models_with_a_cache_write_price": [r["model"] for r in with_writes], "models_with_cached_input_price": len(with_cache),
                  "lowest_cached_multiple": min(with_cache, key=lambda r: r["cached_x_input"])["model"] + " " + str(min(r["cached_x_input"] for r in with_cache)),
                  "highest_cached_multiple": max(with_cache, key=lambda r: r["cached_x_input"])["model"] + " " + str(max(r["cached_x_input"] for r in with_cache)),
                  "write_30m_multiples": sorted({r["write_30m_x_input"] for r in with_writes}), "write_12h_multiples": sorted({r["write_12h_x_input"] for r in with_writes})}
openai_rules = {
    "enabled_by_default_for_supported_models": "Prompt caching is enabled by default for supported OpenAI models" in o_guide_flat,
    "discounted_up_to_95_percent": "discounted up to 95%" in o_guide_flat,
    "gpt_5_6_and_later_min_prefix_1024": "Minimum cacheable prefix | 1,024 visible input tokens" in o_guide_flat,
    "earlier_models_minimum_varies_by_request_settings": "Minimum cacheable prefix | 1,024 visible input tokens | Varies by request settings | Varies by request settings" in o_guide_flat,
    "gpt_5_6_read_0_1x_and_0_05x_for_gpt_6_1_sol": "0.1× uncached input (0.05× for GPT-6.1 Sol)" in o_guide_flat,
    "gpt_5_6_write_1_25x_30m_2_5x_12h": 'Cache write charge | 1.25× for "30m"; 2.5× for "12h" in the Responses API' in o_guide_flat,
    "gpt_5_5_and_earlier_no_additional_write_charge": "No additional cache-write charge | No additional cache-write charge" in o_guide_flat,
    "explicit_breakpoints_gpt_5_6_and_later_only": "Explicit breakpoints | Supported | Not supported | Not supported" in o_guide_flat,
    "mentions_prompt_caching_dashboard": "Prompt Caching Dashboard" in o_guide_flat,
    "mentions_cache_diagnostics_tool": "Prompt Cache Diagnostics" in o_guide_flat,
    "gpt_5_6_default_30m_or_12h_retention": 'Supported retention values | "30m" (default), or "12h" in the Responses API' in o_guide_flat,
    "earlier_models_in_memory_5_to_10_minutes": "Typically 5 to 10 minutes inactive for in_memory" in o_guide_flat,
}

# ---- 3. Google Gemini ----------------------------------------------------------------------------------------
sections = re.split(r"^## ", g_price, flags=re.M)
gemini_models = {}
for sec in sections:
    name = sec.split("\n", 1)[0].strip()
    std = re.search(r"### Standard\n(.*?)(?=\n### |\Z)", sec, re.S)
    if not std:
        continue
    cache = re.search(r"\| Context caching price \|[^|]*\|([^\n]*)\|", std.group(1))
    inp = re.search(r"\| Input price[^|]*\|[^|]*\|([^\n]*)\|", std.group(1))
    if cache and inp:
        gemini_models[name] = {"input_text": inp.group(1).strip()[:160], "context_caching_text": cache.group(1).strip()[:260],
                               "implicit_only": "Implicit caching only" in cache.group(1), "has_storage_price": "storage price" in cache.group(1),
                               "mentions_price_change_date": bool(re.search(r"starting (?:December 1, 2026|January 1, 2027)", cache.group(1)))}
argon = gemini_models.get("Gemini 4 Argon", {})
argon_in = [D(x) for x in re.findall(r"\$([0-9.]+)", argon.get("input_text", ""))]
argon_cache = [D(x) for x in re.findall(r"\$([0-9.]+)", argon.get("context_caching_text", ""))]
gemini_summary = {"models_read": len(gemini_models), "implicit_only_models": sorted(k for k, v in gemini_models.items() if v["implicit_only"]),
                  "models_with_a_storage_price": sorted(k for k, v in gemini_models.items() if v["has_storage_price"]),
                  "models_whose_caching_price_changes_on_a_listed_date": sorted(k for k, v in gemini_models.items() if v["mentions_price_change_date"]),
                  "gemini_4_argon_standard": argon,
                  "gemini_4_argon_cached_x_input_now_and_later": [r4(argon_cache[0] / argon_in[0]), r4(argon_cache[1] / argon_in[1])] if len(argon_in) >= 2 and len(argon_cache) >= 2 else None}
m = re.search(r"Model Min token limit(.*?)To increase the chance", g_doc)
gemini_rules = {"minimum_tokens_table_text": m.group(1).strip()[:300] if m else None,
                "offers_implicit_caching": "offers implicit caching" in g_doc,
                "implicit_and_explicit_both_named": "explicit caching" in g_doc.lower() and "implicit caching" in g_doc.lower()}

# ---- 4. Amazon Bedrock -------------------------------------------------------------------------------------------
bedrock_rules = {"explicit_caching_with_cache_checkpoints": "Explicit Prompt Caching" in bedrock and "cache checkpoints" in bedrock.lower(),
                 "minimums_512_to_4096_per_checkpoint": "Minimums currently range from 512 to 4,096 tokens per cache checkpoint" in bedrock,
                 "mentions_implicit_or_simplified_caching": bool(re.search(r"implicit|simplified cache management", bedrock, re.I)),
                 "prefix_below_minimum_succeeds_but_is_not_cached": "your inference still succeeds, but your prefix isn't cached" in bedrock}

# ---- 5. Our arithmetic: the input side of one reusable prefix ------------------------------------------------------
PREFIX = D(50000)
M = D(10 ** 6)


def row(models, name):
    return next(r for r in models if r["model"] == name)


sonnet = row(anthropic, "Claude Sonnet 5.5")
opus = row(anthropic, "Claude Opus 5.5")
gsol = row(openai_new, "gpt-6-sol")
g55 = row(openai_old + openai_new, "gpt-5.5 (<272K context length)")


def scenario(label, base, first, hit, n_list=(1, 2, 5, 10, 50)):
    """cost of PREFIX tokens over 1 + n requests, uncached vs cached; first = price of the request that writes the cache."""
    out = []
    for n in n_list:
        uncached = PREFIX * D(str(base)) / M * (n + 1)
        cached = PREFIX * (D(str(first)) + D(str(hit)) * n) / M
        out.append({"repeat_requests": n, "uncached_usd": r4(uncached), "cached_usd": r4(cached), "saving_percent": r2((uncached - cached) / uncached * 100)})
    return {"model": label, "base_input": base, "first_request": first, "cache_hit": hit, "rows": out}


def breakeven(base, first, hit):
    """smallest whole number of repeat requests after which caching costs less than not caching."""
    n = 0
    while D(str(first)) + D(str(hit)) * n >= D(str(base)) * (n + 1):
        n += 1
        if n > 1000:
            return None
    return n


arith = {
    "prefix_tokens": int(PREFIX), "assumes": "every repeat request hits the cache; input side only; one prefix; no output tokens",
    "scenarios": [
        {**scenario("Claude Sonnet 5.5, 5-minute write", sonnet["input"], sonnet["write_5m"], sonnet["cache_hit"]), "break_even_repeats": breakeven(sonnet["input"], sonnet["write_5m"], sonnet["cache_hit"])},
        {**scenario("Claude Sonnet 5.5, 1-hour write", sonnet["input"], sonnet["write_1h"], sonnet["cache_hit"]), "break_even_repeats": breakeven(sonnet["input"], sonnet["write_1h"], sonnet["cache_hit"])},
        {**scenario("gpt-6-sol, 30m write", gsol["input"], gsol["write_30m"], gsol["cached_input"]), "break_even_repeats": breakeven(gsol["input"], gsol["write_30m"], gsol["cached_input"])},
        {**scenario("gpt-6-sol, 12h write", gsol["input"], gsol["write_12h"], gsol["cached_input"]), "break_even_repeats": breakeven(gsol["input"], gsol["write_12h"], gsol["cached_input"])},
        {**scenario("gpt-5.5, no write fee", g55["input"], g55["input"], g55["cached_input"]), "break_even_repeats": breakeven(g55["input"], g55["input"], g55["cached_input"])},
    ],
}
if len(argon_in) > 1 and len(argon_cache) > 1:
    for label, i in (("Gemini 4 Argon until 2026-11-30, implicit", 0), ("Gemini 4 Argon from 2026-12-01, implicit", 1)):
        arith["scenarios"].append({**scenario(label, float(argon_in[i]), float(argon_in[i]), float(argon_cache[i])),
                                   "break_even_repeats": breakeven(float(argon_in[i]), float(argon_in[i]), float(argon_cache[i]))})

# ---- 6. Google's AI Overview against the vendors' pages ---------------------------------------------------------------
aio_body = aio.split("\n\n", 1)[1] if "\n\n" in aio else aio   # drop the "# Google AI Overview for ..." header line
aio_claims = {
    "overview_defines_prefix_kv_state_caching": "key-value (KV) states" in aio,
    "overview_says_openai_automatic_from_1024_tokens": "typically starting at 1,024 tokens" in aio,
    "overview_says_discount_50_to_90_percent": "often 50% to 90% cheaper" in aio,
    "overview_says_anthropic_cache_control_5m_or_1h": "5-minute or 1-hour" in aio,
    "overview_says_bedrock_implicit_and_explicit": "both implicit and explicit caching" in aio,
    "overview_mentions_cache_write_charge": bool(re.search(r"cache[- ]write|write (?:price|cost|fee|premium)|1\.25", aio, re.I)),
    "overview_mentions_gemini_or_google": bool(re.search(r"Gemini|Google", aio_body)),
    "overview_mentions_retention_or_ttl_for_openai": bool(re.search(r"24h|12h|30m|prompt_cache_retention", aio)),
    "overview_says_no_quality_loss": "No Quality Loss" in aio,
    "overview_points_to_openai_dashboard": "OpenAI Prompt Caching Dashboard" in aio,
}

json.dump({"as_of": AS_OF, "anthropic_rows": anthropic, "anthropic_summary": anthropic_summary, "anthropic_rules": anthropic_rules,
           "openai_rows_with_write_prices": openai_new, "openai_rows_cached_input_only": openai_old, "openai_summary": openai_summary, "openai_rules": openai_rules,
           "gemini_summary": gemini_summary, "gemini_rules": gemini_rules, "bedrock_rules": bedrock_rules, "arithmetic": arith, "ai_overview_vs_vendor_pages": aio_claims},
          sys.stdout, indent=2, sort_keys=True)
sys.stdout.write("\n")
