#!/usr/bin/env python3
"""Read public records about LM Studio and six alternatives, print one JSON document.

Standard library only, no account, nothing billed, nothing installed or run, no model called. Reads:
  - GitHub's API for six repositories (Jan, Ollama, AnythingLLM, Open WebUI, KoboldCpp, GPT4All): licence (SPDX and the licence file at the
    repository root), archived flag, canonical name, last commit, latest stable release, stable releases in the 90 days before the cut-off,
    published security advisories
  - the repositories in the lmstudio-ai GitHub organisation (LM Studio's app is not one of them), with their licences
  - vendor pages: LM Studio's pricing page, app terms and "free for work" post; Msty's pricing page; ModelPiper's "LM Studio Alternative" article
    and AnythingLLM's "AnythingLLM vs LM Studio" page, which are the two vendor pages Google's AI Overview cites
  - google-ai-overview-lm-studio-alternatives-2026-11-13.md, saved next to this script, to check its claims

Dates use a fixed cut-off (--as-of 2026-11-13T19:30:00Z). Pages are read live. Optional GITHUB_TOKEN lifts GitHub's 60-requests-an-hour limit; the
script makes about 80 GitHub requests, so set it.

Usage: python3 check_lm_studio_alternatives.py [--as-of 2026-11-13T19:30:00Z] > out.json
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
AS_OF = "2026-11-13T19:30:00Z"
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


def find(pattern, text, group=0):
    m = re.search(pattern, text, re.I)
    return m.group(group) if m else None


def gh(path, raw=False):
    h = {"Accept": "application/vnd.github.raw+json" if raw else "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        h["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    st, body = get("https://api.github.com" + path, h)
    if st != 200:
        return "" if raw else {"error": st}
    return body if raw else json.loads(body)


def gh_pages(path, limit=8):
    out = []
    for page in range(1, limit + 1):
        batch = gh(f"{path}{'&' if '?' in path else '?'}per_page=100&page={page}")
        if not isinstance(batch, list):
            return out, False
        out += batch
        if len(batch) < 100:
            return out, True
    return out, False


def gh_cursor(path, limit=8):
    """The security-advisories endpoint paginates by cursor (Link header), and ignores ?page=N."""
    out, url = [], "https://api.github.com" + path + ("&" if "?" in path else "?") + "per_page=100"
    h = {"User-Agent": UA, "Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        h["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    for _ in range(limit):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=40) as r:
                batch = json.loads(r.read().decode("utf-8", "replace"))
                link = r.headers.get("Link") or ""
        except Exception:
            return out, False
        out += batch
        nxt = re.search(r'<([^>]+)>;\s*rel="next"', link)
        if not nxt:
            return out, True
        url = nxt.group(1)
    return out, False


REPOS = [("Jan", "janhq/jan", r"^v\d+\.\d+\.\d+$"),
         ("Ollama", "ollama/ollama", r"^v\d+\.\d+\.\d+$"),
         ("AnythingLLM", "Mintplex-Labs/anything-llm", r"^v\d+\.\d+\.\d+$"),
         ("Open WebUI", "open-webui/open-webui", r"^v\d+\.\d+\.\d+$"),
         ("KoboldCpp", "LostRuins/koboldcpp", r"^v?\d+(?:\.\d+)+$"),
         ("GPT4All", "nomic-ai/gpt4all", r"^v\d+\.\d+\.\d+$")]
LICENCE_PATHS = ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING")


def licence_info(full_name):
    for p in LICENCE_PATHS:
        lic = gh(f"/repos/{full_name}/contents/{p}", raw=True)
        if lic:
            lines = [l.strip() for l in lic.splitlines() if l.strip()]
            return {"found_at_repository_root": p, "first_line": lines[0][:100] if lines else None,
                    "copyright_lines": [l[:100] for l in lines if l.lower().startswith("copyright")][:3],
                    "names_agpl": "GNU AFFERO GENERAL PUBLIC LICENSE" in lic.upper(),
                    "names_apache": "Apache License" in lic, "names_mit": "MIT License" in lic or "MIT license" in lic,
                    "names_bsd": "BSD" in lic.upper()[:600], "mentions_branding": bool(re.search(r"branding", lic, re.I)), "names_fifty_user_branding_exception": "fifty (50)" in lic,
                    "length_chars": len(lic)}
    return {"found_at_repository_root": None}


def repo_row(name, repo, tag_re):
    meta = gh("/repos/" + repo)
    if "error" in meta:
        return {"name": name, "repo": repo, "error": meta["error"]}
    out = {"name": name, "repo": repo, "canonical_repo": meta["full_name"], "stars": meta.get("stargazers_count"),
           "licence_spdx": (meta.get("license") or {}).get("spdx_id"), "archived": meta["archived"],
           "github_description": (meta.get("description") or "")[:160], "licence_file": licence_info(meta["full_name"])}
    commit = gh(f"/repos/{repo}/commits?per_page=1&until={AS_OF}")
    out["last_commit_before_cutoff"] = commit[0]["commit"]["committer"]["date"][:10] if isinstance(commit, list) and commit else None
    all_rels, exhausted = gh_pages(f"/repos/{repo}/releases", 8)
    rels = [r for r in all_rels if isinstance(r, dict) and not r.get("draft") and r.get("published_at") and parse(r["published_at"]) <= CUT]
    stable = sorted((r for r in rels if not r.get("prerelease") and re.search(tag_re, r["tag_name"])
                     and not re.search(r"nightly|alpha|beta|rc|dev|preview|canary", r["tag_name"], re.I)), key=lambda r: r["published_at"])
    oldest = min((r["published_at"] for r in rels), default=None)
    out["latest_stable_release"] = ({"tag": stable[-1]["tag_name"], "date": stable[-1]["published_at"][:10], "days_before_cutoff": (CUT - parse(stable[-1]["published_at"])).days}
                                    if stable else None)
    out["stable_releases_in_90_days"] = sum(1 for r in stable if (CUT - parse(r["published_at"])).days < 90)
    out["release_window_fully_listed"] = bool(exhausted or (oldest and (CUT - parse(oldest)).days >= 90))
    advs, adv_exhausted = gh_cursor(f"/repos/{repo}/security-advisories", 8)
    advs = list({a["ghsa_id"]: a for a in advs if isinstance(a, dict) and a.get("ghsa_id") and a.get("published_at") and parse(a["published_at"]) <= CUT}.values())
    out["advisory_listing_complete"] = adv_exhausted
    out["published_advisories"] = {"total": len(advs), "last_12_months": sum(1 for a in advs if (CUT - parse(a["published_at"])).days < 365),
                                   "by_severity": {s: sum(1 for a in advs if (a.get("severity") or "unknown") == s) for s in sorted({a.get("severity") or "unknown" for a in advs})},
                                   "latest": max((a["published_at"][:10] for a in advs), default=None)}
    return out


rows = [repo_row(*r) for r in REPOS]
by = {r["name"]: r for r in rows}

lm_org = gh("/orgs/lmstudio-ai/repos?per_page=100&sort=pushed")
lm_repos = {r["name"]: {"licence_spdx": (r.get("license") or {}).get("spdx_id"), "archived": r["archived"], "last_push": r["pushed_at"][:10]}
            for r in (lm_org if isinstance(lm_org, list) else []) if r["name"] in ("lms", "lmstudio-js", "lmstudio-python", "lmstudio-bug-tracker", "mlx-engine")}

# ---- Vendor pages ----------------------------------------------------------------------------------------------------------
terms = text_of(get("https://lmstudio.ai/app-terms")[1])
free_work = text_of(get("https://lmstudio.ai/blog/free-for-work")[1])
pricing = text_of(get("https://lmstudio.ai/pricing")[1])
lmstudio = {
    "app_terms": {"company": find(r"(Element Labs, Inc\.)", terms, 1), "version_line": find(r"(Version: [A-Z][a-z]+ \d{1,2}, \d{4})", terms, 1),
                  "licence_grant": find(r"(non-exclusive, non-transferable license to use the Software solely for Your personal and / or internal business purposes)", terms, 1),
                  "says_source_code_is_trade_secret": "source code constitute valuable trade secrets" in terms,
                  "forbids_reverse_engineering": "reverse engineer, decompile, disassemble" in terms},
    "free_for_work_post": {"title": find(r"(LM Studio is free for use at work)", free_work, 1), "date": find(r"((?:Jul|Aug|Jun)[a-z]* \d{1,2}, 2025)", free_work, 1),
                           "says_free_at_home_and_at_work": "free to use both at home and at work" in free_work,
                           "says_no_commercial_licence_needed": "no need to fill a form or contact us" in free_work},
    "pricing_page": {"free": find(r"(Free \$ ?0)", pricing, 1), "bionic_plus": find(r"(Bionic\+ \$ ?20 ?USD / month)", pricing, 1), "pro": find(r"(Pro \$ ?100 ?USD / month)", pricing, 1),
                     "free_includes_local_llms": "Run local LLMs on your machine" in pricing, "title_names_bionic": "Simple plans for LM Studio Bionic" in pricing or "Bionic" in pricing},
    "github_org_repositories": lm_repos}

msty_page = text_of(get("https://msty.ai/pricing")[1])
msty = {"free": find(r"(Free \$0 Forever)", msty_page, 1), "aurum": find(r"(Aurum \$\d+ USD per user / year)", msty_page, 1),
        "aurum_lifetime": find(r"(Aurum Lifetime \$\d+ USD per user)", msty_page, 1), "company": find(r"(Msty is a product of CloudStack, LLC)", msty_page, 1)}

mp = text_of(get("https://modelpiper.com/blog/lm-studio-alternative")[1])
modelpiper = {"title": find(r"(LM Studio Alternative: The Honest List \(2026\))", mp, 1), "author_role": find(r"(Founder & Lead Engineer, ModelPiper)", mp, 1),
              "published": find(r"(August 10, 2026)", mp, 1), "updated": find(r"(Updated October 3, 2026)", mp, 1),
              "times_it_says_ToolPiper": mp.count("ToolPiper"), "times_it_says_ModelPiper": mp.count("ModelPiper"),
              "says_lm_studio_free_for_work_since_july_2025": bool(re.search(r"free for individuals and for work.{0,40}July 2025", mp)),
              "says_bionic_plus_20_and_pro_100": "Bionic+ at $20 a month and Pro at $100 a month" in mp,
              "recommends_toolpiper_for_mac": bool(re.search(r"ToolPiper if you want the runner plus voice, vision and an MCP server on a Mac", mp))}

at = text_of(get("https://anythingllm.com/alternatives/lm-studio")[1])
anything = {"title": find(r"(AnythingLLM vs LM Studio: the open-source LM Studio alternative)", at, 1), "updated": find(r"(Updated [A-Z][a-z]+ \d{4})", at, 1),
            "says_lm_studio_closed_source": "LM Studio is closed source" in at, "says_anythingllm_mit": "MIT-licensed" in at,
            "says_lm_studio_free_for_work": "LM Studio is free, including for work" in at,
            "says_anythingllm_can_use_lm_studio_as_engine": "AnythingLLM can use LM Studio's server" in at or "use LM Studio as its engine" in at,
            "star_claim": find(r"(more than [\d,]+ star)", at, 1), "times_it_says_AnythingLLM": at.count("AnythingLLM")}

# ---- Google's AI Overview ----------------------------------------------------------------------------------------------------
aio = open(os.path.join(HERE, "google-ai-overview-lm-studio-alternatives-2026-11-13.md"), encoding="utf-8").read()
overview_part = aio.split("## Sources cited by the overview")[0]
refs_part = aio.split("## Sources cited by the overview")[1].split("## Organic results")[0]
claims = {
    "overview_names": [n for n in ("Jan", "Ollama", "AnythingLLM", "Msty", "ToolPiper") if n in overview_part],
    "overview_cites_modelpiper_article": "modelpiper.com/blog/lm-studio-alternative" in refs_part,
    "overview_cites_anythingllm_page": "anythingllm.com/alternatives/lm-studio" in refs_part,
    "overview_cites_a_reddit_thread": "reddit.com" in refs_part,
    "overview_says_jan_open_source": bool(re.search(r"open-source, auditable desktop app", overview_part)),
    "overview_mentions_lm_studio_licence_or_price": bool(re.search(r"LM Studio[^.]*(?:free|paid|licen|proprietary|closed)", overview_part, re.I)),
    "overview_mentions_a_dollar_price": bool(re.search(r"\$\d", overview_part)),
    "overview_mentions_security_advisories": bool(re.search(r"advisor|CVE|vulnerab", overview_part, re.I)),
    "overview_has_msty_licence_or_price": bool(re.search(r"Msty[^.]*(?:free|\$|licen)", overview_part, re.I)),
    "jan_github_licence_spdx": by["Jan"].get("licence_spdx"),
    "anythingllm_github_licence_spdx": by["AnythingLLM"].get("licence_spdx"),
    "open_webui_github_licence_spdx": by["Open WebUI"].get("licence_spdx"),
}

json.dump({"as_of": AS_OF, "repositories": rows, "lm_studio": lmstudio, "msty": msty, "modelpiper_article": modelpiper,
           "anythingllm_page": anything, "claims_checked": claims}, sys.stdout, indent=2, sort_keys=True)
sys.stdout.write("\n")
