#!/usr/bin/env python3
"""Read public records about Pydantic AI and LangChain side by side, print one JSON document.

Standard library only, no account, nothing billed, nothing installed or run, no model called. Reads:
  - PyPI JSON API for both families (pydantic-ai, pydantic-ai-slim, pydantic-graph; langchain, langchain-core, langgraph,
    langchain-classic): latest stable version, upload date, stable releases in the 90 days before the cut-off, declared base
    dependencies and declared extras
  - the published wheel of each main package, opened as a zip (never imported or executed): top-level packages, Python file
    count, Python source lines, and whether named modules exist
  - pypistats.org downloads for the last month
  - GitHub: licence, archived flag, last commit before the cut-off, published security advisories, README sentences about
    maintenance status
  - Google's AI Overview for "pydantic ai vs langchain", saved next to this script, to check its checkable claims

Dates use a fixed cut-off (--as-of 2026-10-19T18:30:00Z). Download counts are the trailing month at read time. Optional GITHUB_TOKEN
lifts GitHub's 60-requests-an-hour limit.

Usage: python3 check_pydantic_ai_vs_langchain.py [--as-of 2026-10-19T18:30:00Z] > out.json
"""
import datetime
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import zipfile

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
HERE = os.path.dirname(os.path.abspath(__file__))
AS_OF = "2026-10-19T18:30:00Z"
if "--as-of" in sys.argv:
    AS_OF = sys.argv[sys.argv.index("--as-of") + 1]


def parse(ts):
    return datetime.datetime.strptime(ts[:19] + "Z", "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)


CUT = parse(AS_OF)
STABLE = re.compile(r"^\d+(\.\d+)*$")


def get(url, headers=None, timeout=60, binary=False):
    h = {"User-Agent": UA}
    h.update(headers or {})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
                body = r.read()
                return r.status, (body if binary else body.decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == 2:
                return e.code, (b"" if binary else "")
        except Exception:
            if attempt == 2:
                return 0, (b"" if binary else "")
    return 0, ""


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


def pypi(pkg):
    st, body = get(f"https://pypi.org/pypi/{pkg}/json")
    if st != 200:
        return {"error": st}
    d = json.loads(body)
    rels = d.get("releases", {})
    stable = sorted((files[0]["upload_time_iso_8601"], v) for v, files in rels.items()
                    if files and STABLE.match(v) and parse(files[0]["upload_time_iso_8601"]) <= CUT)
    if not stable:
        return {"error": "no stable release before cut-off"}
    t, v = stable[-1]
    info = json.loads(get(f"https://pypi.org/pypi/{pkg}/{v}/json")[1])["info"]
    base = [re.split(r"[ ;<>=!~\[]", r.strip())[0] for r in (info.get("requires_dist") or []) if "extra ==" not in r]
    time.sleep(1)
    st2, stats = get(f"https://pypistats.org/api/packages/{pkg}/recent")
    return {"latest_stable": v, "uploaded": t[:10], "days_before_cutoff": (CUT - parse(t)).days,
            "versions_in_90_days": sum(1 for tt, _ in stable if (CUT - parse(tt)).days < 90),
            "base_dependencies": sorted(set(base)), "base_dependency_count": len(set(base)),
            "extras": sorted(info.get("provides_extra") or []),
            "requires_python": info.get("requires_python"),
            "downloads_last_month": json.loads(stats)["data"]["last_month"] if st2 == 200 else None}


def wheel(pkg, version):
    """Open the published pure-Python wheel as a zip and describe its contents. Nothing is imported or run."""
    st, body = get(f"https://pypi.org/pypi/{pkg}/{version}/json")
    if st != 200:
        return {"error": st}
    files = [u for u in json.loads(body)["urls"] if u["packagetype"] == "bdist_wheel"]
    if not files:
        return {"error": "no wheel"}
    u = files[0]
    st, blob = get(u["url"], binary=True)
    if st != 200:
        return {"error": st}
    z = zipfile.ZipFile(io.BytesIO(blob))
    names = z.namelist()
    py = [n for n in names if n.endswith(".py")]
    lines = sum(len(z.read(n).decode("utf-8", "replace").splitlines()) for n in py)
    tops = sorted({n.split("/")[0] for n in names if "/" in n and not n.split("/")[0].endswith((".dist-info", ".data"))})
    return {"wheel_file": u["filename"], "wheel_bytes": u["size"], "python_files": len(py), "python_lines": lines,
            "top_level_packages": tops, "names": names}


PROJECTS = [("LangChain", "langchain", "langchain-ai/langchain"), ("Pydantic AI", "pydantic-ai-slim", "pydantic/pydantic-ai"),
            ("LangGraph", "langgraph", "langchain-ai/langgraph")]
STATUS = re.compile(r"[^.>|\n]*(?:maintenance mode|is deprecated|now deprecated|no longer (?:actively )?(?:maintained|supported)|"
                    r"successor|superseded|replaced by|archived)[^.\n]*\.?", re.I)


def repo_row(name, pkg, repo):
    out = {"name": name, "package": pkg, "repo": repo}
    meta = gh("/repos/" + repo)
    if "error" in meta:
        out["github"] = {"error": meta["error"]}
        return out
    commit = gh(f"/repos/{repo}/commits?per_page=1&until={AS_OF}")
    advs = [a for a in gh_pages(f"/repos/{repo}/security-advisories") if isinstance(a, dict) and a.get("published_at") and parse(a["published_at"]) <= CUT]
    readme = re.sub(r"\s+", " ", gh(f"/repos/{repo}/readme", raw=True))
    out["github"] = {
        "canonical_repo": meta["full_name"], "licence_spdx": (meta.get("license") or {}).get("spdx_id"), "archived": meta["archived"],
        "last_commit_before_cutoff": commit[0]["commit"]["committer"]["date"][:10] if isinstance(commit, list) and commit else None,
        "published_advisories": {"total": len(advs), "last_12_months": sum(1 for a in advs if (CUT - parse(a["published_at"])).days < 365),
                                 "by_severity": {s: sum(1 for a in advs if (a.get("severity") or "unknown") == s) for s in sorted({a.get("severity") or "unknown" for a in advs})},
                                 "latest": max((a["published_at"][:10] for a in advs), default=None)},
        "readme_status_sentences": [s.strip()[:220] for s in STATUS.findall(readme)][:3],
        "advisory_list": [{"id": a["ghsa_id"], "cve": a.get("cve_id"), "severity": a.get("severity"), "published": a["published_at"][:10],
                           "summary": (a.get("summary") or "")[:140]} for a in sorted(advs, key=lambda a: a["published_at"], reverse=True)[:6]],
    }
    return out


# ---- 1. Packaging of both families --------------------------------------------------------------
FAMILY = ["langchain", "langchain-core", "langgraph", "langchain-classic", "pydantic-ai", "pydantic-ai-slim", "pydantic-graph"]
# First-party packages that a plain `pip install langchain` / `pip install pydantic-ai-slim` pulls in, found by following the declared
# base dependencies one level at a time. Shared third-party packages (pydantic, httpx, opentelemetry, pyyaml...) are excluded.
FIRST_PARTY = {
    "LangChain": ["langchain", "langchain-core", "langgraph", "langgraph-prebuilt", "langgraph-checkpoint", "langgraph-sdk", "langchain-protocol", "langsmith"],
    "Pydantic AI": ["pydantic-ai-slim", "pydantic-graph", "genai-prices", "logfire-api"],
}
EXTRA = [p for ps_ in FIRST_PARTY.values() for p in ps_ if p not in FAMILY]
registry = {p: pypi(p) for p in FAMILY + EXTRA}

# ---- 2. What the published wheels contain ----------------------------------------------------------
WHEELS = {p: wheel(p, registry[p]["latest_stable"]) for p in sorted(set(("langchain-classic",) + tuple(q for ps_ in FIRST_PARTY.values() for q in ps_)))}
contents = {}
for p, w in WHEELS.items():
    names = w.pop("names", [])
    contents[p] = w
    if p == "langchain":
        w["has_chains_package"] = any(n.startswith("langchain/chains/") for n in names)
        w["has_agents_package"] = any(n.startswith("langchain/agents/") for n in names)
    if p == "langchain-classic":
        w["has_chains_package"] = any(n.startswith("langchain_classic/chains/") for n in names)
    if p == "langchain-core":
        w["has_runnables_package"] = any(n.startswith("langchain_core/runnables/") for n in names)
    if p == "pydantic-ai-slim":
        w["has_langchain_tool_adapter"] = any(n == "pydantic_ai/ext/langchain.py" for n in names)
        w["has_logfire_instrumentation"] = any("logfire" in n for n in names)
        w["has_graph_dependency_declared"] = "pydantic-graph" in registry["pydantic-ai-slim"]["base_dependencies"]

first_party_totals = {}
for fam, pkgs in FIRST_PARTY.items():
    ok = [p for p in pkgs if "error" not in contents[p]]
    first_party_totals[fam] = {"packages": pkgs, "packages_measured": ok,
                               "versions": {p: registry[p]["latest_stable"] for p in pkgs},
                               "wheel_bytes": sum(contents[p]["wheel_bytes"] for p in ok),
                               "python_files": sum(contents[p]["python_files"] for p in ok),
                               "python_lines": sum(contents[p]["python_lines"] for p in ok)}

# ---- 3. Repositories ---------------------------------------------------------------------------------
repos = [repo_row(*p) for p in PROJECTS]

# ---- 4. Claims in Google's AI Overview ---------------------------------------------------------------
aio = open(os.path.join(HERE, "google-ai-overview-pydantic-ai-vs-langchain-2026-10-19.md"), encoding="utf-8").read()
ps = registry["pydantic-ai-slim"]["extras"]
lc = registry["langchain"]
claims = {
    "overview_says_langchain_uses_lcel_and_custom_chains": bool(re.search(r"LCEL", aio)) and bool(re.search(r"custom chains", aio)),
    "langchain_wheel_has_chains_package": contents["langchain"]["has_chains_package"],
    "langchain_classic_wheel_has_chains_package": contents["langchain-classic"]["has_chains_package"],
    "overview_says_600_plus_integrations": "600+" in aio,
    "overview_names_pydantic_ai_providers": ["OpenAI", "Anthropic", "Gemini", "Ollama", "Groq", "Mistral"],
    "pydantic_ai_slim_extras_for_those_providers": sorted(e for e in ps if e in ("openai", "anthropic", "google", "groq", "mistral", "ollama")),
    "overview_says_logfire_builtin": "Logfire" in aio,
    "pydantic_ai_slim_extra_logfire": "logfire" in ps,
    "overview_suggests_hybrid_use": "Hybrid Approach" in aio,
    "pydantic_ai_ships_langchain_tool_adapter": contents["pydantic-ai-slim"]["has_langchain_tool_adapter"],
    "langchain_extras_count": len(lc["extras"]),
    "pydantic_ai_slim_extras_count": len(ps),
}

json.dump({"as_of": AS_OF, "registry": registry, "wheel_contents": contents, "first_party_totals": first_party_totals, "repositories": repos, "claims_checked": claims},
          sys.stdout, indent=2, sort_keys=True)
sys.stdout.write("\n")
