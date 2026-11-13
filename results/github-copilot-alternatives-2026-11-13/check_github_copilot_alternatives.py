#!/usr/bin/env python3
"""Read public records about GitHub Copilot and its alternatives, print one JSON document.

Standard library only, no account, nothing billed, nothing installed or run, no model called. Reads:
  - GitHub's API for four open-source alternatives (Aider, Continue, Cline, OpenCode): licence (SPDX and the licence file at the repository
    root), archived flag, canonical name, stars, last commit, newest GitHub release marker, non-draft releases in the 90 days before the
    cut-off, published security advisories; PyPI for Aider's package
  - vendor pages: GitHub Copilot's plans page, Cursor's pricing page, Devin's pricing page (where windsurf.com/pricing now lands),
    Amazon Q Developer's pricing page, Cognition's "Windsurf is now Devin Desktop" post and Devin's Desktop FAQ
  - where windsurf.com, codeium.com, windsurf.com/pricing and tabnine.com/pricing redirect (final URL after redirects)
  - google-ai-overview-github-copilot-alternatives-2026-11-13.md, saved next to this script, to check its claims

Dates use a fixed cut-off (--as-of 2026-11-13T19:30:00Z). Pages are read live. Optional GITHUB_TOKEN lifts GitHub's 60-requests-an-hour limit.

Usage: python3 check_github_copilot_alternatives.py [--as-of 2026-11-13T19:30:00Z] > out.json
"""
import datetime
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
HERE = os.path.dirname(os.path.abspath(__file__))
AS_OF = "2026-11-13T19:30:00Z"
if "--as-of" in sys.argv:
    AS_OF = sys.argv[sys.argv.index("--as-of") + 1]


def parse(ts):
    return datetime.datetime.strptime(ts[:19] + "Z", "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)


CUT = parse(AS_OF)


def get(url, headers=None, timeout=40, want_final=False):
    h = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
    h.update(headers or {})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
                body = r.read().decode("utf-8", "replace")
                return (r.status, body, r.geturl()) if want_final else (r.status, body)
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == 2:
                return (e.code, "", url) if want_final else (e.code, "")
        except Exception:
            if attempt == 2:
                return (0, "", url) if want_final else (0, "")
    return (0, "", url) if want_final else (0, "")


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


REPOS = [("Aider", "Aider-AI/aider"), ("Continue", "continuedev/continue"), ("Cline", "cline/cline"), ("OpenCode", "sst/opencode")]
LICENCE_PATHS = ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING")


def licence_info(full_name):
    for p in LICENCE_PATHS:
        lic = gh(f"/repos/{full_name}/contents/{p}", raw=True)
        if lic:
            lines = [l.strip() for l in lic.splitlines() if l.strip()]
            return {"found_at_repository_root": p, "first_line": lines[0][:100] if lines else None,
                    "copyright_lines": [l[:100] for l in lines if l.lower().startswith("copyright")][:3],
                    "names_apache": "Apache License" in lic, "names_mit": "MIT License" in lic or "MIT license" in lic,
                    "names_agpl": "GNU AFFERO GENERAL PUBLIC LICENSE" in lic.upper()}
    return {"found_at_repository_root": None}


def pypi_row(pkg):
    st, body = get(f"https://pypi.org/pypi/{pkg}/json")
    if st != 200:
        return {"package": pkg, "error": st}
    rels = json.loads(body).get("releases", {})
    stable = sorted((files[0]["upload_time_iso_8601"], v) for v, files in rels.items()
                    if files and re.fullmatch(r"\d+(\.\d+)*", v) and parse(files[0]["upload_time_iso_8601"]) <= CUT)
    t, v = stable[-1]
    return {"package": pkg, "latest_stable": v, "uploaded": t[:10], "versions_in_90_days": sum(1 for tt, _ in stable if (CUT - parse(tt)).days < 90)}


def repo_row(name, repo):
    meta = gh("/repos/" + repo)
    if "error" in meta:
        return {"name": name, "repo": repo, "error": meta["error"]}
    out = {"name": name, "repo": repo, "canonical_repo": meta["full_name"], "stars": meta.get("stargazers_count"),
           "licence_spdx": (meta.get("license") or {}).get("spdx_id"), "archived": meta["archived"],
           "github_description": (meta.get("description") or "")[:160], "licence_file": licence_info(meta["full_name"])}
    commit = gh(f"/repos/{repo}/commits?per_page=1&until={AS_OF}")
    out["last_commit_before_cutoff"] = commit[0]["commit"]["committer"]["date"][:10] if isinstance(commit, list) and commit else None
    rels, exhausted = gh_pages(f"/repos/{repo}/releases", 8)
    rels = [r for r in rels if isinstance(r, dict) and not r.get("draft") and r.get("published_at") and parse(r["published_at"]) <= CUT]
    oldest = min((r["published_at"] for r in rels), default=None)
    latest = gh(f"/repos/{repo}/releases/latest")
    out["github_latest_release_marker"] = ({"tag": latest["tag_name"], "date": latest["published_at"][:10], "days_before_cutoff": (CUT - parse(latest["published_at"])).days}
                                           if isinstance(latest, dict) and "tag_name" in latest else None)
    out["non_draft_releases_in_90_days"] = sum(1 for r in rels if (CUT - parse(r["published_at"])).days < 90)
    out["release_window_fully_listed"] = bool(exhausted or (oldest and (CUT - parse(oldest)).days >= 90))
    advs, adv_exhausted = gh_cursor(f"/repos/{repo}/security-advisories", 8)
    advs = list({a["ghsa_id"]: a for a in advs if isinstance(a, dict) and a.get("ghsa_id") and a.get("published_at") and parse(a["published_at"]) <= CUT}.values())
    out["advisory_listing_complete"] = adv_exhausted
    out["published_advisories"] = {"total": len(advs), "last_12_months": sum(1 for a in advs if (CUT - parse(a["published_at"])).days < 365),
                                   "by_severity": {s: sum(1 for a in advs if (a.get("severity") or "unknown") == s) for s in sorted({a.get("severity") or "unknown" for a in advs})},
                                   "latest": max((a["published_at"][:10] for a in advs), default=None)}
    out["registry"] = pypi_row("aider-chat") if name == "Aider" else None
    return out


rows = [repo_row(*r) for r in REPOS]
by = {r["name"]: r for r in rows}

# ---- Redirects ------------------------------------------------------------------------------------------------------------
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def chain(url, hops=6):
    """Follow redirects by hand and return the list of URLs visited with the status of the last hop."""
    opener = urllib.request.build_opener(_NoRedirect)
    seen = [url]
    status = None
    for _ in range(hops):
        try:
            r = opener.open(urllib.request.Request(seen[-1], headers={"User-Agent": UA}), timeout=30)
            status = r.status
            break
        except urllib.error.HTTPError as e:
            status = e.code
            loc = e.headers.get("Location")
            if e.code in (301, 302, 303, 307, 308) and loc:
                seen.append(urllib.parse.urljoin(seen[-1], loc))
                continue
            break
        except Exception:
            status = 0
            break
    return {"visited": seen, "last_status": status}


redirects = {u: chain(u) for u in ("https://windsurf.com/pricing", "https://windsurf.com", "https://codeium.com", "https://www.tabnine.com/pricing")}

# ---- Vendor pages ----------------------------------------------------------------------------------------------------------
cp = text_of(get("https://github.com/features/copilot/plans")[1])
copilot = {"free": find(r"For getting started with GitHub Copilot\. (\$ ?0 ?USD)", cp, 1), "pro": find(r"For everyday coding with agents in GitHub Copilot\. (\$ ?\d+ ?USD ?per user / month)", cp, 1),
           "pro_plus": find(r"For more complex development with premium models\. (\$ ?\d+ ?USD ?per user / month)", cp, 1),
           "max": find(r"For sustained, high-volume agent workflows with GitHub Copilot\. (\$ ?\d+ ?USD ?per user / month)", cp, 1),
           "pro_credits": find(r"(\$15 monthly total credits for Pro)", cp, 1), "pro_plus_credits": find(r"(\$70 monthly total credits for Pro\+)", cp, 1),
           "max_credits": find(r"(\$200 monthly total credits for Max)", cp, 1),
           "free_completions": find(r"(2,000 completions per month)", cp, 1),
           "pro_includes_third_party_agents": "Access to 3rd party agents (Claude Code and Codex)" in cp,
           "pro_plus_premium_models_incl_opus": "Access to premium models, including Opus" in cp,
           "uses_github_ai_credits_term": "GitHub AI Credits" in cp}

cu = text_of(get("https://cursor.com/pricing")[1])
cursor = {"free": find(r"(Free \$0 ?/ ?month)", cu, 1), "plus": find(r"(Plus \$8 ?/ ?month)", cu, 1), "premium": find(r"(Premium (?:Most popular )?\$30 ?/ ?month)", cu, 1),
          "super": find(r"(Super \$100 ?/ ?month)", cu, 1), "ultra": find(r"(Ultra \$200 ?/ ?month)", cu, 1),
          "says_third_party_models_billed_separately": "billed separately by usage" in cu, "page_mentions_grok": "Grok" in cu}

dv = text_of(get("https://devin.ai/pricing")[1])
devin = {"title": find(r"(Devin Plans and Pricing)", dv, 1), "free": find(r"(Free \$0)", dv, 1), "pro": find(r"(Pro ?POPULAR \$20 ?per month)", dv, 1) or find(r"(\$20 ?per month)", dv, 1),
         "max": find(r"(\$200 ?per month)", dv, 1), "teams": find(r"(\$80 ?/ ?month for team plan \+ \$40 ?/ ?mo per full dev seat)", dv, 1),
         "free_has_unlimited_tab_completions": "Unlimited Tab completions" in dv, "mentions_windsurf": "Windsurf" in dv}

blog = text_of(get("https://devin.ai/blog/windsurf-is-now-devin-desktop")[1])
faq = text_of(get("https://docs.devin.ai/desktop/devin-desktop-faq")[1])
windsurf = {"blog_title": find(r"(Windsurf is now Devin Desktop)", blog, 1), "blog_date": find(r"(June 2, 2026)", blog, 1),
            "blog_says_next_generation_of_windsurf": "next generation of Windsurf" in blog,
            "blog_says_cascade_available_through_july_1": "legacy Cascade agent through July 1st" in blog,
            "faq_says_new_name_for_windsurf": "Devin Desktop is the new name for Windsurf" in faq,
            "faq_says_pricing_unchanged": "Pricing is unchanged" in faq, "faq_date": find(r"(On June 2, 2026, Windsurf is becoming Devin Desktop)", faq, 1)}

aq = text_of(get("https://aws.amazon.com/q/developer/pricing/")[1])
amazon_q = {"pro_price": find(r"(Pro Tier: Expanded limits \$\d+/mo\. per user)", aq, 1), "free_requests": find(r"(50 agentic requests per month)", aq, 1),
            "free_tier_line": find(r"(Free Tier: Advanced capabilities at zero cost)", aq, 1)}

# ---- Google's AI Overview ----------------------------------------------------------------------------------------------------
aio = open(os.path.join(HERE, "google-ai-overview-github-copilot-alternatives-2026-11-13.md"), encoding="utf-8").read()
overview_part = aio.split("## Sources cited by the overview")[0]
refs_part = aio.split("## Sources cited by the overview")[1].split("## Organic results")[0]
claims = {
    "overview_names": [n for n in ("Cursor", "Windsurf", "Claude Code", "Aider", "OpenCode", "Continue.dev", "Codeium", "Tabnine", "Amazon Q Developer", "Gemini Code Assist", "Sourcegraph") if n in overview_part],
    "overview_lists_windsurf_and_codeium_separately": "**Windsurf:**" in overview_part and "**Codeium:**" in overview_part,
    "overview_mentions_devin_or_cognition": bool(re.search(r"Devin|Cognition", overview_part)),
    "overview_mentions_a_copilot_price": bool(re.search(r"\$\d", overview_part)),
    "overview_mentions_tricentis": "Tricentis" in overview_part,
    "overview_says_codeium_free_for_individuals": "Free for individual developers" in overview_part,
    "overview_says_cursor_supports_gpt_4": "GPT-4" in overview_part,
    "overview_mentions_spacex_or_grok_for_cursor": bool(re.search(r"SpaceX|Grok", overview_part)),
    "overview_cites_reddit": "reddit.com" in refs_part, "overview_cites_digitalocean": "digitalocean.com" in refs_part,
    "overview_cites_gartner": "gartner.com" in refs_part, "overview_cites_pecollective": "pecollective.com" in refs_part,
}

json.dump({"as_of": AS_OF, "repositories": rows, "redirects": redirects, "github_copilot": copilot, "cursor": cursor, "devin": devin,
           "windsurf_rename": windsurf, "amazon_q_developer": amazon_q, "claims_checked": claims}, sys.stdout, indent=2, sort_keys=True)
sys.stdout.write("\n")
