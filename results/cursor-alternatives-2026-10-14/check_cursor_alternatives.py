#!/usr/bin/env python3
"""Read public records about Cursor and nine alternatives, print one JSON document.

Standard library only, no account, nothing billed, nothing installed or run, no model called. Reads:
  - Cursor's own blog post about its acquisition and its pricing page
  - Windsurf's pricing page (windsurf.com now serves the "Devin Desktop" site) and Zed's pricing page
  - GitHub's API for eight repositories: licence, language, archived flag, last commit before the cut-off, latest stable
    release, stable releases in the 90 days before the cut-off, and README sentences that say whether the project
    is maintained, deprecated, read-only or moved
  - the licence files at the root of the Zed repository
  - Google's AI Overview for "cursor alternatives", saved next to this script, to check three of its claims

Dates use a fixed cut-off (--as-of 2026-10-14T17:30:00Z), so two runs agree. Pages and READMEs are read live.
Optional GITHUB_TOKEN lifts GitHub's 60-requests-an-hour limit; the script makes about 40 GitHub requests.

Usage: python3 check_cursor_alternatives.py [--as-of 2026-10-14T17:30:00Z] > out.json
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
AS_OF = "2026-10-14T17:30:00Z"
if "--as-of" in sys.argv:
    AS_OF = sys.argv[sys.argv.index("--as-of") + 1]


def parse(ts):
    return datetime.datetime.strptime(ts[:19] + "Z", "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)


CUT = parse(AS_OF)


def get(url, headers=None, timeout=40):
    h = {"User-Agent": UA}
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


# ---- 1. Closed products: Cursor, Windsurf, Zed pricing --------------------------------------------------
post = text_of(get("https://cursor.com/blog/joining-spacex")[1])
pricing = text_of(get("https://cursor.com/pricing")[1])
blog_index = text_of(get("https://cursor.com/blog")[1])
cursor = {
    "acquisition_post": "https://cursor.com/blog/joining-spacex",
    "post_date": find(r"([A-Z][a-z]{2} \d{1,2}, 2026) · company Cursor is now a part of SpaceX", post, 1),
    "says_acquired_by_spacex": "Cursor has officially been acquired by SpaceX" in post,
    "says_process_started": find(r"(This completes the acquisition process that started in [A-Za-z]+, when we announced our partnership with SpaceXAI[^.]*\.)", post, 1),
    "individual_plans": sorted({(n, int(p)) for n, p in re.findall(r"\b(Free|Plus|Premium|Super|Ultra) \$(\d+) /month", pricing)}, key=lambda t: t[1]),
    "teams_price": find(r"Teams \$(\d+) \+?/user/month", pricing, 1),
    "plus_plan_note": find(r"(\*Only Grok models are available on this plan)", pricing, 1),
    "third_party_models_note": find(r"(Third Party model usage in Cursor is not included in the monthly prices shown and must be purchased separately)", pricing, 1),
    "pricing_page_lists_non_coding_features": [f for f in ("Post, reply, and follow", "Premium checkmark", "Less timeline ads") if f in pricing],
    "blog_lists_grok_models": bool(re.search(r"Introducing Grok 4\.\d", blog_index)),
}
wind_home = text_of(get("https://windsurf.com/")[1])
wind = text_of(get("https://windsurf.com/pricing")[1])
windsurf = {
    "site_title": find(r"^(Devin Desktop[^|]*)\|", wind_home, 1),
    "free": find(r"Free \$(\d+) Download", wind, 1),
    "pro_per_month": find(r"Pro POPULAR \$(\d+) per month", wind, 1),
    "max_per_month": find(r"Max NEW \$(\d+) per month", wind, 1),
    "teams": find(r"(Teams \$\d+ /month for team plan \+ \$\d+/mo per full dev seat)", wind, 1),
    "models_sentence": find(r"(access to frontier models from [^,]*, [^,]*, [^,]*, and [A-Za-z]+, plus leading open source models)", wind, 1),
}
zp = text_of(get("https://zed.dev/pricing")[1])
zed_page = {
    "pro_per_month": find(r"Pro Free Trial \$(\d+) per month", zp, 1),
    "pro_tokens_included": find(r"\$(\d+) of tokens included", zp, 1),
    "business_per_seat": find(r"Business \$(\d+) per seat", zp, 1),
    "free_with_own_keys": "Free forever. Unlimited use with your API keys" in zp,
}

# ---- 2. Repositories ----------------------------------------------------------------------------------
# name, repo, tag regex of the main product
REPOS = [("Cline", "cline/cline", r"^v\d+\.\d+\.\d+$"), ("Kilo Code", "Kilo-Org/kilocode", r"^v\d+\.\d+\.\d+$"),
         ("Zed", "zed-industries/zed", r"^v\d+\.\d+\.\d+$"), ("VS Code", "microsoft/vscode", r"^\d+\.\d+\.\d+$"),
         ("VS Code Copilot Chat", "microsoft/vscode-copilot-chat", r"^v\d+\.\d+\.\d+$"),
         ("Continue", "continuedev/continue", r"^v\d+\.\d+\.\d+-vscode$"),
         ("Roo Code", "RooCodeInc/Roo-Code", r"^v\d+\.\d+\.\d+$"), ("Void", "voideditor/void", r"^v?\d+\.\d+\.\d+$")]
STATUS = re.compile(r"[^.>|\n]*(?:no longer (?:actively )?(?:maintained|supported)|is deprecated|now deprecated|read-only|moved into|"
                    r"archived|final \d+\.\d+\.\d+ release)[^.\n]*\.?", re.I)


def repo_row(name, repo, tag_re):
    meta = gh("/repos/" + repo)
    if "error" in meta:
        return {"name": name, "repo": repo, "error": meta["error"]}
    out = {"name": name, "repo": repo, "canonical_repo": meta["full_name"], "licence_spdx": (meta.get("license") or {}).get("spdx_id"),
           "language": meta.get("language"), "archived": meta["archived"]}
    commit = gh(f"/repos/{repo}/commits?per_page=1&until={AS_OF}")
    out["last_commit_before_cutoff"] = commit[0]["commit"]["committer"]["date"][:10] if isinstance(commit, list) and commit else None
    rels = [r for r in gh_pages(f"/repos/{repo}/releases") if not r.get("draft") and r.get("published_at") and parse(r["published_at"]) <= CUT]
    stable = sorted((r for r in rels if not r.get("prerelease") and re.search(tag_re, r["tag_name"])
                     and not re.search(r"nightly|alpha|beta|rc|dev|preview|canary", r["tag_name"], re.I)), key=lambda r: r["published_at"])
    out["latest_stable_release_before_cutoff"] = ({"tag": stable[-1]["tag_name"], "date": stable[-1]["published_at"][:10],
                                                    "days_before_cutoff": (CUT - parse(stable[-1]["published_at"])).days} if stable else None)
    out["stable_releases_in_90_days"] = sum(1 for r in stable if (CUT - parse(r["published_at"])).days < 90)
    newest = max(rels, key=lambda r: r["published_at"], default=None)
    out["latest_release_of_any_kind"] = ({"tag": newest["tag_name"], "date": newest["published_at"][:10], "prerelease": bool(newest.get("prerelease"))}
                                         if newest else None)
    out["all_releases_are_prereleases"] = bool(rels) and all(r.get("prerelease") for r in rels)
    advs = gh_pages(f"/repos/{repo}/security-advisories")
    advs = [a for a in advs if isinstance(a, dict) and a.get("published_at") and parse(a["published_at"]) <= CUT]
    out["published_advisories"] = {"total": len(advs), "last_12_months": sum(1 for a in advs if (CUT - parse(a["published_at"])).days < 365),
                                   "by_severity": {s: sum(1 for a in advs if (a.get("severity") or "unknown") == s)
                                                   for s in sorted({a.get("severity") or "unknown" for a in advs})},
                                   "latest": max((a["published_at"][:10] for a in advs), default=None)}
    readme = re.sub(r"\s+", " ", gh(f"/repos/{repo}/readme", raw=True))
    out["readme_status_sentences"] = [s.strip()[:220] for s in STATUS.findall(readme)][:3]
    return out


rows = [repo_row(*r) for r in REPOS]
by = {r["name"]: r for r in rows}
roo_home = text_of(get("https://roocode.com/")[1])
roo_site = {"homepage_headline": find(r"^(Roomote: [^|]*?)(?: Product| Cloud agents)", roo_home, 1),
            "homepage_says_by_the_creators_of": find(r"(By the creators of [A-Za-z ]{3,20}?)(?: The cloud| \w+ cloud)", roo_home, 1),
            "homepage_mentions_roo_code_extension": "Roo Code" in roo_home}
zed_files = {f:(gh(f"/repos/zed-industries/zed/contents/{f}", raw=True).strip().splitlines() or [""])[0].strip()
             for f in ("LICENSE-GPL", "LICENSE-APACHE")}
zed_files = {k: v for k, v in zed_files.items() if v}

# ---- 3. Claims in Google's AI Overview ------------------------------------------------------------------
aio = open(os.path.join(HERE, "google-ai-overview-cursor-alternatives-2026-10-14.md"), encoding="utf-8").read()
claims = {
    "overview_names_roo_void_or_continue": [n for n in ("Roo Code", "Void", "Continue") if n in aio],
    "overview_says_cline_apache_2_0": "Cline" in aio and "Apache-2.0" in aio, "github_licence_for_cline": by["Cline"].get("licence_spdx"),
    "overview_says_kilo_mit": "(MIT)" in aio, "github_licence_for_kilo": by["Kilo Code"].get("licence_spdx"),
    "overview_zed_pro_10_dollars": "$10/mo Pro" in aio, "zed_pricing_page_pro": zed_page["pro_per_month"],
    "overview_windsurf_20_dollars": "($20/mo)" in aio, "windsurf_pricing_page_pro": windsurf["pro_per_month"],
    "overview_names_spacex_or_ownership": bool(re.search(r"SpaceX|acquired|owned", aio)),
}

json.dump({"as_of": AS_OF, "cursor": cursor, "windsurf": windsurf, "zed_pricing": zed_page, "zed_licence_files": zed_files, "roo_code_site": roo_site,
           "repositories": rows, "claims_checked": claims}, sys.stdout, indent=2, sort_keys=True)
sys.stdout.write("\n")
