#!/usr/bin/env python3
"""Read public records about seven agent-memory libraries, print one JSON document.

Standard library only, no account, nothing is billed and no memory library is installed, imported or run.
Reads, per project:
  - GitHub API: licence, language, archived flag, last commit before the cut-off, latest stable release,
    releases in the last 90 days, published security advisories, open-issue count
  - PyPI JSON API: latest version before the cut-off, upload date, versions in the last 90 days,
    number of declared dependencies, required Python, install-time extras named
  - pypistats.org: downloads over the last month (a public, unauthenticated API)
It also checks four claims in Google's AI Overview, saved next to this script.

Dates use a fixed cut-off (--as-of 2026-10-12T19:00:00Z), so two runs agree. Optional GITHUB_TOKEN lifts
GitHub's 60-requests-an-hour limit; the script makes about 40 GitHub requests, so set it.

Usage: python3 check_agent_memory.py [--as-of 2026-10-12T19:00:00Z] > out.json
"""
import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
HERE = os.path.dirname(os.path.abspath(__file__))
AS_OF = "2026-10-12T19:00:00Z"
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


def gh(path):
    h = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        h["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    st, body = get("https://api.github.com" + path, h)
    return json.loads(body) if st == 200 else {"error": st}


def gh_pages(path, limit=5):
    out = []
    for page in range(1, limit + 1):
        sep = "&" if "?" in path else "?"
        batch = gh(f"{path}{sep}per_page=100&page={page}")
        if not isinstance(batch, list):
            return out if out else batch
        out += batch
        if len(batch) < 100:
            break
    return out


# name, GitHub repo, PyPI package, tag pattern of the main product
PROJECTS = [
    ("Mem0", "mem0ai/mem0", "mem0ai", r"^v\d+\.\d+\.\d+$"),
    ("Graphiti (Zep's open-source engine)", "getzep/graphiti", "graphiti-core", r"^v\d+\.\d+\.\d+$"),
    ("Zep (repository)", "getzep/zep", None, r"^v\d+\.\d+\.\d+$"),
    ("Letta (formerly MemGPT)", "letta-ai/letta", "letta", r"^\d+\.\d+\.\d+$"),
    ("Letta Code (current Letta source)", "letta-ai/letta-code", None, r"v?\d+\.\d+\.\d+$"),
    ("LangMem", "langchain-ai/langmem", "langmem", r"^v\d+\.\d+\.\d+$"),
    ("Cognee", "topoteretes/cognee", "cognee", r"^v\d+\.\d+\.\d+$"),
    ("Supermemory", "supermemoryai/supermemory", None, r"^v\d+\.\d+\.\d+$"),
]


def pypi_row(pkg):
    st, body = get(f"https://pypi.org/pypi/{pkg}/json")
    if st != 200:
        return {"package": pkg, "error": st}
    d = json.loads(body)
    rels = d.get("releases", {})
    stable = sorted((files[0]["upload_time_iso_8601"], v) for v, files in rels.items()
                    if files and not re.search(r"[a-z]", v) and parse(files[0]["upload_time_iso_8601"]) <= CUT)
    if not stable:
        return {"package": pkg, "error": "no stable release before cut-off"}
    t, v = stable[-1]
    meta = rels[v][0]
    info = get(f"https://pypi.org/pypi/{pkg}/{v}/json")
    info = json.loads(info[1])["info"] if info[0] == 200 else d["info"]
    requires = info.get("requires_dist") or []
    base = [r for r in requires if "extra ==" not in r]
    extras = sorted({m for r in requires for m in re.findall(r"extra == ['\"]([^'\"]+)['\"]", r)})
    st2, stats = get(f"https://pypistats.org/api/packages/{pkg}/recent")
    month = json.loads(stats)["data"]["last_month"] if st2 == 200 else None
    return {"package": pkg, "summary": info.get("summary"), "source_url": (info.get("project_urls") or {}).get("Source"),
            "latest_stable": v, "uploaded": t[:10], "days_before_cutoff": (CUT - parse(t)).days,
            "versions_in_90_days": sum(1 for tt, _ in stable if (CUT - parse(tt)).days < 90),
            "required_python": info.get("requires_python"), "dependencies_without_extras": len(base),
            "optional_extras": len(extras), "downloads_last_month": month,
            "wheel_or_sdist": meta.get("packagetype")}


def repo_row(name, repo, pkg, tag_re):
    meta = gh("/repos/" + repo)
    if "error" in meta:
        return {"name": name, "repo": repo, "error": meta["error"]}
    out = {"name": name, "repo": repo, "canonical_repo": meta["full_name"],
           "licence_spdx": (meta.get("license") or {}).get("spdx_id"), "language": meta.get("language"),
           "archived": meta["archived"], "created": meta["created_at"][:10]}
    commit = gh(f"/repos/{repo}/commits?per_page=1&until={AS_OF}")
    out["last_commit_before_cutoff"] = commit[0]["commit"]["committer"]["date"][:10] if isinstance(commit, list) and commit else None
    releases = [r for r in gh_pages(f"/repos/{repo}/releases") if isinstance(r, dict) and not r.get("draft")
                and r.get("published_at") and parse(r["published_at"]) <= CUT]
    stable_rel = [r for r in releases if not r.get("prerelease") and re.search(tag_re, r["tag_name"])
                  and not re.search(r"nightly|alpha|beta|rc|dev|preview", r["tag_name"], re.I)]
    stable_rel.sort(key=lambda r: r["published_at"])
    out["latest_stable_release_before_cutoff"] = ({"tag": stable_rel[-1]["tag_name"], "date": stable_rel[-1]["published_at"][:10],
                                                    "days_before_cutoff": (CUT - parse(stable_rel[-1]["published_at"])).days}
                                                   if stable_rel else None)
    out["stable_releases_in_90_days"] = sum(1 for r in stable_rel if (CUT - parse(r["published_at"])).days < 90)
    advs = gh_pages(f"/repos/{repo}/security-advisories")
    if isinstance(advs, list):
        advs = [a for a in advs if a.get("published_at") and parse(a["published_at"]) <= CUT]
        sev = {}
        for a in advs:
            sev[a.get("severity") or "unknown"] = sev.get(a.get("severity") or "unknown", 0) + 1
        out["published_advisories"] = {"total": len(advs), "by_severity": dict(sorted(sev.items())),
                                       "latest": max((a["published_at"][:10] for a in advs), default=None),
                                       "list": [{"id": a["ghsa_id"], "severity": a.get("severity"), "published": a["published_at"][:10],
                                                 "cve": a.get("cve_id"), "summary": a.get("summary"),
                                                 "patched": [v.get("patched_versions") for v in a.get("vulnerabilities", [])]}
                                                for a in sorted(advs, key=lambda a: a["published_at"])]}
    else:
        out["published_advisories"] = {"error": advs.get("error") if isinstance(advs, dict) else "unavailable"}
    # README sentences that say whether the project is the maintained product or a pointer elsewhere
    readme = get(f"https://raw.githubusercontent.com/{repo}/HEAD/README.md")[1]
    out["readme_mentions_deprecated_or_sunset"] = bool(re.search(r"deprecat|sunset|no longer (maintained|supported)|end[- ]of[- ]life", readme, re.I))
    flat = re.sub(r"\s+", " ", readme)
    out["readme_status_sentences"] = [m.strip()[:240] for m in re.findall(
        r"([^.|>]*(?:current source code lives in|retired|no longer supported|is \*\*not\*\* Zep's product|Kuzu is \*\*deprecated\*\*)[^.]*\.)", flat)][:4]
    if pkg:
        out["pypi"] = pypi_row(pkg)
    return out


rows = [repo_row(*p) for p in PROJECTS]

# ---- Claims in Google's AI Overview ------------------------------------------------------------------
by = {r["name"]: r for r in rows}
aio = open(os.path.join(HERE, "google-ai-overview-ai-agent-memory-2026-10-12.md"), encoding="utf-8").read()
mem0 = by["Mem0"]
claims = {
    "overview_calls_mem0_drop_in_production_layer": "drop-in production memory layer" in aio,
    "mem0_licence_spdx": mem0.get("licence_spdx"),
    "mem0_stable_releases_in_90_days": mem0.get("stable_releases_in_90_days"),
    "overview_names_no_zep_letta_langmem_or_cognee": not any(n in aio for n in ("Zep", "Letta", "LangMem", "Cognee")),
    "overview_cites_vendor_domains": sorted(set(re.findall(r"\b(mem0\.ai|redis\.io|ibm\.com)\b", aio))),
}

result = {"as_of": AS_OF, "projects": rows, "claims_checked": claims}
json.dump(result, sys.stdout, indent=2, sort_keys=True)
sys.stdout.write("\n")
