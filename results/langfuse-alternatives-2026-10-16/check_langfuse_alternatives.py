#!/usr/bin/env python3
"""Read public records about Langfuse and nine alternatives, print one JSON document.

Standard library only, no account, nothing billed, nothing installed or run, no model called. Reads:
  - three announcements: Langfuse joining ClickHouse, Helicone joining Mintlify, Traceloop joining ServiceNow
  - the licence file at the root of the Langfuse, Phoenix, Opik and MLflow repositories (first line and copyright line)
  - Comet's Opik pricing page (free tier), to check a claim in Google's AI Overview
  - GitHub's API for nine repositories: licence, archived flag, last commit before the cut-off, latest stable release,
    stable releases in the 90 days before the cut-off, published security advisories, and README sentences that say
    whether the project is deprecated, in maintenance mode or moved
  - PyPI's JSON API for the Python packages: latest stable version, upload date, versions in 90 days
  - Google's AI Overview for "langfuse alternatives", saved next to this script, to check four of its claims

Dates use a fixed cut-off (--as-of 2026-10-16T18:30:00Z), so two runs agree. Pages and READMEs are read live.
Optional GITHUB_TOKEN lifts GitHub's 60-requests-an-hour limit; the script makes about 60 GitHub requests.

Usage: python3 check_langfuse_alternatives.py [--as-of 2026-10-16T18:30:00Z] > out.json
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
AS_OF = "2026-10-16T18:30:00Z"
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


# ---- 1. Three announcements ---------------------------------------------------------------------
ch = text_of(get("https://clickhouse.com/blog/clickhouse-acquires-langfuse-open-source-llm-observability")[1])
lf = text_of(get("https://langfuse.com/blog/joining-clickhouse")[1])
hel = text_of(get("https://www.helicone.ai/blog/joining-mintlify")[1])
tl = text_of(get("https://traceloop.com/blog/traceloop-is-joining-servicenow")[1])
announcements = {
    "langfuse_clickhouse": {
        "clickhouse_post_date": find(r"((?:Jan|Feb|Mar) \d{1,2}, 2026) · \d+ minutes read", ch, 1),
        "clickhouse_says": find(r"(ClickHouse has acquired Langfuse)", ch, 1),
        "langfuse_says_open_source_and_self_hostable": "Langfuse stays open source and self‑hostable" in lf or "Langfuse stays open source and self-hostable" in lf,
        "langfuse_says_no_planned_licence_change": "There are no planned changes to licensing" in lf,
        "langfuse_says_cloud_unchanged": "Langfuse Cloud keeps running as‑is" in lf or "Langfuse Cloud keeps running as-is" in lf,
    },
    "helicone_mintlify": {
        "date": find(r"((?:Jan|Feb|Mar) \d{1,2}, 2026) · \d+ minute read", hel, 1),
        "says_acquired": find(r"(Helicone has been acquired by Mintlify)", hel, 1),
        "maintenance_mode_sentence": find(r"(Helicone's services will remain live for the foreseeable future in maintenance mode\.)", hel, 1),
        "keeps_shipping_sentence": find(r"(This means security updates, new models, bug & performance fixes all keep shipping\.)", hel, 1),
    },
    "traceloop_servicenow": {
        "date": find(r"(Co-Founder and CEO • ([A-Za-z]+ 2026))", tl, 2),
        "says_joining": find(r"(Traceloop is joining ServiceNow)", tl, 1),
        "says_becomes_part_of": find(r"(our technology will become part of ServiceNow's AI Control Tower)", tl, 1),
    },
}

# ---- 2. Licence files and Opik's free tier --------------------------------------------------------
licence_files = {}
for name, repo in (("Langfuse", "langfuse/langfuse"), ("Phoenix", "Arize-ai/phoenix"), ("Opik", "comet-ml/opik"), ("MLflow", "mlflow/mlflow")):
    lines = [l.strip() for l in gh(f"/repos/{repo}/contents/LICENSE", raw=True).splitlines() if l.strip()]
    licence_files[name] = {"first_line": lines[0][:100] if lines else None,
                           "copyright_line": next((l[:100] for l in lines if l.lower().startswith("copyright")), None),
                           "has_ee_carve_out": any('"ee/"' in l for l in lines)}
comet = text_of(get("https://www.comet.com/site/pricing/")[1])
opik_pricing = {
    "free_cloud": find(r"Free Cloud Perfect for individuals \$(\d+) Free plan", comet, 1),
    "free_spans_per_month": find(r"Up to \d+ team members (\d+k) spans per month", comet, 1),
    "pro_per_month": find(r"Pro Cloud Popular Expanded usage for teams \$(\d+) Per month", comet, 1),
    "pro_spans_per_month": find(r"Up to 50 team members (\d+k) spans per month", comet, 1),
    "open_source_same_codebase_claim": "True OSS: same codebase as the hosted versions" in comet,
}

# ---- 3. Repositories ------------------------------------------------------------------------------
REPOS = [("Langfuse", "langfuse/langfuse", "langfuse", r"^v\d+\.\d+\.\d+$"),
         ("Arize Phoenix", "Arize-ai/phoenix", "arize-phoenix", r"^arize-phoenix-v\d+\.\d+\.\d+$"),
         ("Opik", "comet-ml/opik", "opik", r"^\d+\.\d+\.\d+$"),
         ("MLflow", "mlflow/mlflow", "mlflow", r"^v\d+\.\d+\.\d+$"),
         ("Helicone", "Helicone/helicone", None, r"^v\d{4}\.\d{2}\.\d{2}"),
         ("Laminar", "lmnr-ai/lmnr", "lmnr", r"^v?\d+\.\d+\.\d+$"),
         ("OpenLLMetry", "traceloop/openllmetry", "traceloop-sdk", r"^v?\d+\.\d+\.\d+$"),
         ("OpenLIT", "openlit/openlit", "openlit", r"^v?\d+\.\d+\.\d+$"),
         ("W&B Weave", "wandb/weave", "weave", r"^v?\d+\.\d+\.\d+$")]
STATUS = re.compile(r"[^.>|\n]*(?:maintenance mode|is deprecated|now deprecated|no longer (?:actively )?(?:maintained|supported)|"
                    r"part of [A-Z][A-Za-z]+|archived|since January 2026 we.re part of [A-Za-z]+)[^.\n]*\.?", re.I)


def pypi_row(pkg):
    st, body = get(f"https://pypi.org/pypi/{pkg}/json")
    if st != 200:
        return {"package": pkg, "error": st}
    rels = json.loads(body).get("releases", {})
    stable = sorted((files[0]["upload_time_iso_8601"], v) for v, files in rels.items()
                    if files and re.fullmatch(r"\d+(\.\d+)*", v) and parse(files[0]["upload_time_iso_8601"]) <= CUT)
    if not stable:
        return {"package": pkg, "error": "no stable release before cut-off"}
    t, v = stable[-1]
    return {"package": pkg, "latest_stable": v, "uploaded": t[:10], "days_before_cutoff": (CUT - parse(t)).days,
            "versions_in_90_days": sum(1 for tt, _ in stable if (CUT - parse(tt)).days < 90)}


def repo_row(name, repo, pkg, tag_re):
    meta = gh("/repos/" + repo)
    if "error" in meta:
        return {"name": name, "repo": repo, "error": meta["error"]}
    out = {"name": name, "repo": repo, "canonical_repo": meta["full_name"], "licence_spdx": (meta.get("license") or {}).get("spdx_id"),
           "archived": meta["archived"]}
    commit = gh(f"/repos/{repo}/commits?per_page=1&until={AS_OF}")
    out["last_commit_before_cutoff"] = commit[0]["commit"]["committer"]["date"][:10] if isinstance(commit, list) and commit else None
    rels = [r for r in gh_pages(f"/repos/{repo}/releases") if not r.get("draft") and r.get("published_at") and parse(r["published_at"]) <= CUT]
    stable = sorted((r for r in rels if not r.get("prerelease") and re.search(tag_re, r["tag_name"])
                     and not re.search(r"nightly|alpha|beta|rc|dev|preview|canary", r["tag_name"], re.I)), key=lambda r: r["published_at"])
    out["latest_stable_release_before_cutoff"] = ({"tag": stable[-1]["tag_name"], "date": stable[-1]["published_at"][:10],
                                                    "days_before_cutoff": (CUT - parse(stable[-1]["published_at"])).days} if stable else None)
    out["stable_releases_in_90_days"] = sum(1 for r in stable if (CUT - parse(r["published_at"])).days < 90)
    advs = [a for a in gh_pages(f"/repos/{repo}/security-advisories") if isinstance(a, dict) and a.get("published_at") and parse(a["published_at"]) <= CUT]
    out["published_advisories"] = {"total": len(advs), "last_12_months": sum(1 for a in advs if (CUT - parse(a["published_at"])).days < 365),
                                   "by_severity": {s: sum(1 for a in advs if (a.get("severity") or "unknown") == s)
                                                   for s in sorted({a.get("severity") or "unknown" for a in advs})},
                                   "latest": max((a["published_at"][:10] for a in advs), default=None)}
    readme = re.sub(r"\s+", " ", gh(f"/repos/{repo}/readme", raw=True))
    out["readme_status_sentences"] = [s.strip()[:220] for s in STATUS.findall(readme)][:3]
    if pkg:
        out["pypi"] = pypi_row(pkg)
    return out


rows = [repo_row(*r) for r in REPOS]
by = {r["name"]: r for r in rows}

# ---- 4. Claims in Google's AI Overview ------------------------------------------------------------------
aio = open(os.path.join(HERE, "google-ai-overview-langfuse-alternatives-2026-10-16.md"), encoding="utf-8").read()
claims = {
    "overview_names_helicone": "Helicone" in aio,
    "overview_mentions_mintlify_or_maintenance_mode": bool(re.search(r"Mintlify|maintenance mode", aio)),
    "overview_mentions_clickhouse": "ClickHouse" in aio,
    "overview_says_opik_apache_2_0": "Apache 2.0" in aio, "github_licence_for_opik": by["Opik"].get("licence_spdx"),
    "overview_says_opik_free_25000_spans": "25,000 spans per month" in aio, "opik_pricing_page_free_spans": opik_pricing["free_spans_per_month"],
    "overview_mentions_phoenix_licence": bool(re.search(r"Elastic|source-available", aio)),
    "overview_names_traceloop_or_openllmetry": bool(re.search(r"Traceloop|OpenLLMetry", aio)),
}

json.dump({"as_of": AS_OF, "announcements": announcements, "licence_files": licence_files, "opik_pricing": opik_pricing,
           "repositories": rows, "claims_checked": claims}, sys.stdout, indent=2, sort_keys=True)
sys.stdout.write("\n")
