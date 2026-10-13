#!/usr/bin/env python3
"""Read Google's public pages about Gemini 4 Argon and print one JSON document.

Standard library only, no account, nothing billed, and no model is called. Reads:
  - the DeepMind model card (benchmark table, distribution list, knowledge cutoff, FSF notes)
  - the two Google blog posts (2026-09-30 announcement, 2026-10-13 availability post)
  - the Gemini API pricing page and models page (endpoint name, per-tier prices, price step-up date)
  - Artificial Analysis' model page (independent index score and rank)
It then counts, from the model card's own table, on how many benchmarks Argon is highest among the four
models Google chose to show, and where it is not.

Pages change; the output records what each page said when read. Usage: python3 check_argon.py > out.json
"""
import html
import json
import re
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"


def raw(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60).read().decode("utf-8", "replace")


def text_of(page):
    page = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", "", page)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page))).strip()


def find(pattern, text, group=0):
    m = re.search(pattern, text, re.I)
    return m.group(group) if m else None


# ---- 1. Model card ------------------------------------------------------------------------------
card_html = raw("https://deepmind.google/models/model-cards/gemini-4-argon/")
card = text_of(card_html)
table = card_html[card_html.find("<table"):card_html.find("</table>")]
models = [text_of(h) for h in re.findall(r"<th[^>]*scope=col[^>]*>(.*?)</th>", table.split("</thead>")[0])][3:]
rows = []
name = None
for tr in re.findall(r"<tr>(.*?)</tr>", table.split("</thead>")[1], re.S):
    # A benchmark cell can span two rows (GraphWalks), so a row without one inherits the previous name.
    m = re.search(r"<td class=table--benchmark[^>]*>(.*?)</td>", tr, re.S)
    if m:
        name = text_of(m.group(1))
    note = text_of(find(r"<td class=table--notes[^>]*>(.*?)</td>", tr, 1) or "")
    value_cells = [text_of(c) for attrs, c in re.findall(r"<td([^>]*)>(.*?)</td>", tr, re.S)
                   if "table--benchmark" not in attrs and "table--notes" not in attrs]
    vals = []
    for c in value_cells:
        v = find(r"([\d.]+)%", c, 1)
        vals.append(float(v) if v else None)
    if len(vals) != 4:
        raise SystemExit("unexpected table row shape: %r" % tr[:200])
    rows.append({"benchmark": name, "note": note or None, "values": dict(zip(models, vals))})
argon = models[0]
for r in rows:
    nums = {k: v for k, v in r["values"].items() if v is not None}
    best = max(nums.values())
    r["highest"] = sorted(k for k, v in nums.items() if v == best)
    r["argon_is_highest"] = nums.get(argon) == best
wins = [r["benchmark"] for r in rows if r["argon_is_highest"]]
losses = [{"benchmark": r["benchmark"], "highest": r["highest"], "argon": r["values"][argon], "best": r["values"][r["highest"][0]]}
          for r in rows if not r["argon_is_highest"]]
card_out = {
    "published_line": find(r"Published (\d+ \w+ \d{4})", card, 1),
    "models_in_table": models,
    "benchmark_rows": len(rows),
    "argon_highest_on": len(wins),
    "argon_not_highest_on": len(losses),
    "losses": losses,
    "rows_with_a_missing_value": [r["benchmark"] for r in rows if any(v is None for v in r["values"].values())],
    "knowledge_cutoff": find(r"knowledge cutoff for Gemini 4 is ([A-Za-z]+ \d{4})", card, 1),
    "context_window": find(r"context window of up to (\w+)", card),
    "architecture": "sparse mixture-of-experts" if "sparse mixture-of-experts" in card else None,
    "channels_listed": [c for c in ("Gemini App", "Gemini API", "Google AI Studio", "Gemini for business", "Google Antigravity", "Google AI Mode") if c in card],
    "says_not_modification_of_prior_model": "not a modification or a fine-tune of a prior model" in card,
    "safety_report_stated_as_coming_soon": "coming soon on October 13th" in card,
    "cbrn_ccl_sentence": find(r"(CBRN CCL: [^.]*\.)", card, 1),
    "cyber_ccl_sentence": find(r"(Cyber[^.]{0,40}CCL[^.]*\.)", card, 1),
    "evals_footer_says_scores_are_vendor_reported": "Gemini 4 Argon results as of October, 2026" in card,
}

# ---- 2. The two blog posts --------------------------------------------------------------------------
ann = text_of(raw("https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-4-argon/"))
avail = text_of(raw("https://blog.google/innovation-and-ai/models-and-research/gemini-models/introducing-gemini-4-argon/"))
blog_out = {
    "announcement_date": find(r"(Sep \d+, 2026) \|", ann, 1),
    "announcement_access": find(r"rolling out to ([^.]*?)(?: through| via)[^.]*\.", ann, 0),
    "announcement_says_phased_release": "phased approach" in ann,
    "announcement_price": find(r"introductory price 1 of (\$\d+ per million input tokens and \$\d+ per million output tokens)", ann, 1),
    "availability_date": find(r"(Oct \d+, 2026) \|", avail, 1),
    "availability_access": find(r"(Gemini 4 Argon is now globally available today[^.]*\.)", avail, 1),
    "post_introductory_price": find(r"(After the introductory period expires on [A-Za-z]+ \d+, 2026, the price of \$\d+ per 1M input tokens and \$\d+ per 1M output tokens will apply)", avail, 1),
    "cached_input_discount": find(r"cached input tokens at (\d+% off)", avail, 1),
    "unified_input_output_limit": find(r"industry-leading (\w+) unified input-output token limit", avail, 1),
    "vals_index_claim": find(r"(ranking #1 on the Vals Index)", avail, 1),
    "chrome_refactor_claim": find(r"(~6 million line legacy folder)", avail, 1),
    "adk_claims": find(r"(cut in-memory session prep time by \d+% in long sessions and sped up cold imports by \d+%)", avail, 1),
    "shortcut_attempt_claim": find(r"(shortcut attempts dropped to just \d+%)", avail, 1),
    "prompt_injection_claim": find(r"(cutting attack success across 15 adaptive attempts to [\d.]+%)", avail, 1),
    "fairwind_expansion_sentence": find(r"(Starting today, we.re beginning expansion to hundreds of additional Fairwind Program partners)", avail, 1),
    "external_third_party_view_footnote": "Views in this blog are of the external party" in avail,
}

# ---- 3. Developer pricing and models pages ----------------------------------------------------------
pricing = text_of(raw("https://ai.google.dev/gemini-api/docs/pricing"))
models_pg = text_of(raw("https://ai.google.dev/gemini-api/docs/models"))
seg = pricing[pricing.find("Gemini 4 Argon gemini-4-argon"):]
seg = seg[:seg.find("Gemini 3.8 Flash")] if "Gemini 3.8 Flash" in seg else seg[:6000]
tiers = {}
for tier in ("Standard", "Batch", "Flex", "Priority"):
    part = seg[seg.find(tier + " Free Tier"):]
    nxt = [part.find(t + " Free Tier") for t in ("Standard", "Batch", "Flex", "Priority") if t != tier and part.find(t + " Free Tier") > 0]
    part = part[:min(nxt)] if nxt else part[:900]
    tiers[tier] = {
        "input": find(r"Input price Not available (\$[\d.]+ through [A-Za-z]+ \d+, 2026\. \$[\d.]+ starting [A-Za-z]+ \d+, 2026)", part, 1),
        "output": find(r"Output price \(including thinking tokens\) Not available (\$[\d.]+ through [A-Za-z]+ \d+, 2026\. \$[\d.]+ starting [A-Za-z]+ \d+, 2026)", part, 1),
        "cached_input": find(r"Context caching price Not available (\$[\d.]+ through [A-Za-z]+ \d+, 2026\. \$[\d.]+ starting [A-Za-z]+ \d+, 2026)", part, 1),
    }
pricing_out = {
    "endpoint_on_models_page": "gemini-4-argon" if "gemini-4-argon" in models_pg else None,
    "not_available_on_free_tier_or_ai_pro_plan": "not available on the Free tier or on the Google AI Pro plan" in seg,
    "caching": "Implicit caching only (explicit caching is not supported)" in seg,
    "tiers": tiers,
}

# ---- 4. Independent index ---------------------------------------------------------------------------
aa = text_of(raw("https://artificialanalysis.ai/models/gemini-4-argon"))
aa_out = {
    "intelligence_index": find(r"Intelligence # (\d+) / (\d+) (\d+) Artificial Analysis Intelligence Index", aa, 3),
    "rank": find(r"Intelligence # (\d+) / (\d+)", aa, 1),
    "of_models": find(r"Intelligence # (\d+) / (\d+)", aa, 2),
    "median_of_comparable_models": find(r"median: (\d+)\)", aa, 1),
    "cost_per_index_task_usd": find(r"costs \$([\d.]+) per task", aa, 1),
    "output_tokens_used_for_index": find(r"it generated ([\d.]+M) tokens", aa, 1),
    "index_version": find(r"Intelligence Index (v[\d.]+)", aa, 1),
    "speed": "N/A" if "Speed N/A" in aa else None,
}

json.dump({"model_card": card_out, "model_card_rows": rows, "blog": blog_out, "pricing": pricing_out, "artificial_analysis": aa_out},
          __import__("sys").stdout, indent=2, sort_keys=True)
print()
