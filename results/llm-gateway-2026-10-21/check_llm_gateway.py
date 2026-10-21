#!/usr/bin/env python3
"""Read public records about nine open-source LLM gateways and four ownership changes, print one JSON document.

Standard library only, no account, nothing billed, no gateway installed, run or called, no model called. Reads:
  - GitHub for nine gateway repositories: licence (SPDX and the LICENSE file's first lines), main language, archived flag, last commit,
    latest stable release, releases in the last 90 days, published security advisories, and how often the README mentions
    ten feature words (a count of mentions, not a test that the feature works)
  - Palo Alto Networks' release on the Portkey acquisition and Stripe's announcement about OpenRouter
  - LiteLLM's own incident notice (docs.litellm.ai)
  - llmgateway.io's home page, for the model and provider counts Google's AI Overview repeats
  - google-ai-overview-llm-gateway-2026-10-21.md, saved next to this script, to check its claims

Dates use a fixed cut-off (--as-of 2026-10-21T19:00:00Z). Page text and advisories are read live. Optional GITHUB_TOKEN lifts GitHub's
60-requests-an-hour limit; the script makes about 70 GitHub requests, so set it.

Usage: python3 check_llm_gateway.py [--as-of 2026-10-21T19:00:00Z] > out.json
"""
import datetime
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
HERE = os.path.dirname(os.path.abspath(__file__))
AS_OF = "2026-10-21T19:00:00Z"
if "--as-of" in sys.argv:
    AS_OF = sys.argv[sys.argv.index("--as-of") + 1]


def parse(ts):
    return datetime.datetime.strptime(ts[:19] + "Z", "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)


CUT = parse(AS_OF)


def get(url, headers=None, timeout=40):
    h = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
    h.update(headers or {})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == 2:
                return e.code, ""
        except Exception:
            if attempt == 2:
                return 0, ""
    return 0, ""


def text_of(page):
    page = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", "", page)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page))).strip()


def gh(path, raw=False):
    h = {"Accept": "application/vnd.github.raw+json" if raw else "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        h["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    st, body = get("https://api.github.com" + path, h)
    if st != 200:
        return "" if raw else {"error": st}
    return body if raw else json.loads(body)


def gh_pages(path, limit=5):
    out = []
    for page in range(1, limit + 1):
        batch = gh(f"{path}{'&' if '?' in path else '?'}per_page=100&page={page}")
        if not isinstance(batch, list):
            return out
        out += batch
        if len(batch) < 100:
            break
    return out


def find(pattern, text, group=0):
    m = re.search(pattern, text, re.I)
    return m.group(group) if m else None


FEATURES = {"openai_compatible": r"OpenAI[- ]compatible|OpenAI API|OpenAI format", "fallbacks": r"fallback|failover", "load_balancing": r"load[- ]balanc",
            "caching": r"\bcach(?:e|ing)\b", "semantic_caching": r"semantic cach", "guardrails": r"guardrail", "rate_limits": r"rate[- ]limit",
            "budgets_or_spend": r"budget|spend", "virtual_keys": r"virtual key|API key management", "observability": r"observab|tracing|logging", "mcp": r"\bMCP\b"}

# name, repo, tag pattern of the main product
REPOS = [("LiteLLM", "BerriAI/litellm", r"^v\d+\.\d+\.\d+$"), ("Portkey gateway", "Portkey-AI/gateway", r"^v\d+\.\d+\.\d+$"),
         ("Bifrost", "maximhq/bifrost", r"^transports/v\d+\.\d+\.\d+$"), ("Kong Gateway", "Kong/kong", r"^\d+\.\d+\.\d+$"),
         ("Envoy AI Gateway", "envoyproxy/ai-gateway", r"^v\d+\.\d+\.\d+$"), ("Helicone", "Helicone/helicone", r"^v\d{4}\.\d{2}\.\d{2}"),
         ("TensorZero", "tensorzero/tensorzero", r"^\d{4}\.\d+\.\d+$"), ("LLM Gateway (llmgateway.io)", "theopenco/llmgateway", r"^v?\d+\.\d+\.\d+$"),
         ("agentgateway", "agentgateway/agentgateway", r"^v\d+\.\d+\.\d+$")]


def repo_row(name, repo, tag_re):
    meta = gh("/repos/" + repo)
    if "error" in meta:
        return {"name": name, "repo": repo, "error": meta["error"]}
    out = {"name": name, "repo": repo, "canonical_repo": meta["full_name"], "licence_spdx": (meta.get("license") or {}).get("spdx_id"),
           "language": meta.get("language"), "archived": meta["archived"], "description": (meta.get("description") or "")[:140]}
    default = meta.get("default_branch") or "main"
    lic = get(f"https://raw.githubusercontent.com/{meta['full_name']}/{default}/LICENSE")[1]
    out["licence_file_first_lines"] = " ".join(lic.split("\n")[:3])[:200] if lic else None
    out["licence_file_says_agplv3_outside_carve_out"] = bool(re.search(r"available under the .?AGPLv3.? license", lic or ""))
    out["licence_file_says_mit_outside_carve_out"] = bool(re.search(r"available under the MIT license", lic or ""))
    out["licence_file_mentions_enterprise_or_commercial_carve_out"] = bool(re.search(r"ee/|enterprise/|Commercial License|Enterprise Edition", lic or "", re.I))
    commit = gh(f"/repos/{repo}/commits?per_page=1&until={AS_OF}")
    out["last_commit_before_cutoff"] = commit[0]["commit"]["committer"]["date"][:10] if isinstance(commit, list) and commit else None
    rels = [r for r in gh_pages(f"/repos/{repo}/releases") if isinstance(r, dict) and not r.get("draft") and r.get("published_at") and parse(r["published_at"]) <= CUT]
    stable = sorted((r for r in rels if not r.get("prerelease") and re.search(tag_re, r["tag_name"]) and not re.search(r"nightly|alpha|beta|rc|dev|preview", r["tag_name"], re.I)),
                    key=lambda r: r["published_at"])
    out["latest_stable_release"] = ({"tag": stable[-1]["tag_name"], "date": stable[-1]["published_at"][:10], "days_before_cutoff": (CUT - parse(stable[-1]["published_at"])).days}
                                    if stable else None)
    out["stable_releases_in_90_days"] = sum(1 for r in stable if (CUT - parse(r["published_at"])).days < 90)
    advs = [a for a in gh_pages(f"/repos/{repo}/security-advisories") if isinstance(a, dict) and a.get("published_at") and parse(a["published_at"]) <= CUT]
    out["published_advisories"] = {"total": len(advs), "last_12_months": sum(1 for a in advs if (CUT - parse(a["published_at"])).days < 365),
                                   "by_severity": {s: sum(1 for a in advs if (a.get("severity") or "unknown") == s) for s in sorted({a.get("severity") or "unknown" for a in advs})},
                                   "latest": max((a["published_at"][:10] for a in advs), default=None)}
    readme = re.sub(r"\s+", " ", gh(f"/repos/{repo}/readme", raw=True))
    out["readme_chars"] = len(readme)
    out["readme_mentions"] = {k: len(re.findall(p, readme, re.I)) for k, p in FEATURES.items()}
    return out


repos = [repo_row(*r) for r in REPOS]
by = {r["name"]: r for r in repos}

# ---- Ownership changes and incidents, from primary sources ------------------------------------------------
pan = text_of(get("https://www.paloaltonetworks.com/company/press/2026/palo-alto-networks-completes-acquisition-of-portkey-to-secure-ai-agents")[1])
stripe = text_of(get("https://stripe.com/newsroom/news/stripe-agrees-to-acquire-openrouter")[1])
lt = text_of(get("https://docs.litellm.ai/blog/security-update-march-2026")[1])
ownership = {
    "portkey_palo_alto": {"url": "https://www.paloaltonetworks.com/company/press/2026/palo-alto-networks-completes-acquisition-of-portkey-to-secure-ai-agents",
                          "says_completed_acquisition_of_portkey": "closed the acquisition of Portkey" in pan or "completes acquisition of Portkey" in pan.lower() or "completed its acquisition of Portkey" in pan,
                          "release_date": find(r"((?:January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, 2026) -- Palo Alto", pan, 1)},
    "openrouter_stripe": {"url": "https://stripe.com/newsroom/news/stripe-agrees-to-acquire-openrouter",
                          "headline_says_agrees_to_acquire": "Stripe agrees to acquire OpenRouter" in stripe,
                          "release_date": find(r"(\d{1,2} (?:January|February|March|April|May|June|July|August|September|October|November|December) 2026)", stripe, 1),
                          "says_a_leading_ai_model_gateway_and_routing_platform": "a leading AI model gateway and routing platform" in stripe,
                          "says_400_models_80_providers": "400+ models from more than 80 providers" in stripe},
    "litellm_incident": {"url": "https://docs.litellm.ai/blog/security-update-march-2026", "published": find(r"Published: ([A-Z][a-z]{2} \d{1,2}, \d{4})", lt, 1),
                         "compromised_versions_named": sorted(set(re.findall(r"litellm==(1\.\d+\.\d+)", lt))),
                         "docker_proxy_image_not_impacted": "official LiteLLM Proxy Docker image were not impacted" in lt},
    "agent_router_rename": {"envoyproxy_ai_gateway_resolves_to": by["Envoy AI Gateway"].get("canonical_repo")},
    "tensorzero_archived": by["TensorZero"].get("archived"),
}

# ---- Google's AI Overview and the product it names --------------------------------------------------------------------
aio = open(os.path.join(HERE, "google-ai-overview-llm-gateway-2026-10-21.md"), encoding="utf-8").read()
lg_home = text_of(get("https://llmgateway.io/")[1])
claims = {
    "overview_defines_gateway_as_unified_middleware_layer": "unified middleware layer" in aio,
    "overview_says_openai_compatible_api": "OpenAI-compatible" in aio,
    "overview_lists_functions": [f for f in ("Unified API", "Smart Routing", "Failover", "Cost", "Caching", "Security", "Guardrails") if f in aio],
    "overview_names_platforms": [p for p in ("LLM Gateway", "LiteLLM", "Bifrost", "Kong", "Portkey") if p in aio],
    "overview_says_250_models_40_providers": "250+ models across 40+ providers" in aio,
    "llmgateway_io_home_says_250_models": "250+" in lg_home, "llmgateway_io_home_says_40_providers": "40+" in lg_home,
    "llmgateway_io_licence_spdx": by["LLM Gateway (llmgateway.io)"].get("licence_spdx"),
    "llmgateway_io_licence_file_first_lines": by["LLM Gateway (llmgateway.io)"].get("licence_file_first_lines"),
    "overview_calls_litellm_lightweight_python": "Lightweight or quick-setup options ideal for Python apps" in aio,
    "github_language_for_litellm": by["LiteLLM"].get("language"), "github_description_for_litellm": by["LiteLLM"].get("description"),
    "overview_calls_kong_portkey_enterprise_grade": "Enterprise-grade" in aio,
    "overview_mentions_portkey_acquisition": bool(re.search(r"Palo Alto|acquir", aio, re.I)),
    "overview_mentions_litellm_march_2026_incident": bool(re.search(r"incident|compromis|supply chain", aio, re.I)),
    "overview_mentions_openrouter_or_stripe": [n for n in ("OpenRouter", "Stripe") if n in aio],
    "overview_mentions_any_archived_or_renamed_project": [n for n in ("TensorZero", "Envoy", "Agent Router") if n in aio],
}

json.dump({"as_of": AS_OF, "repositories": repos, "ownership_and_incidents": ownership, "claims_checked": claims}, sys.stdout, indent=2, sort_keys=True)
sys.stdout.write("\n")
