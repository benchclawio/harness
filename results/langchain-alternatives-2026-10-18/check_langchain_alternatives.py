#!/usr/bin/env python3
"""Read public records about LangChain's packaging and twelve alternatives, print one JSON document.

Standard library only, no account, nothing billed, nothing installed or run, no model called. Reads:
  - PyPI JSON API for the LangChain family (langchain, langchain-core, langgraph, langchain-classic, langchain-community):
    version, upload date and the declared base dependencies, to show what "leaving LangChain" leaves behind
  - per project: PyPI (or the npm registry for the two TypeScript projects) for latest stable version, upload date and stable
    releases in the 90 days before the cut-off; pypistats.org / npm downloads for the last month; GitHub for licence, archived
    flag, last commit before the cut-off, published security advisories and README sentences about maintenance status
  - Google's AI Overview for "langchain alternatives", saved next to this script, to check three of its claims

Dates use a fixed cut-off (--as-of 2026-10-18T18:30:00Z). Download counts are the trailing month at read time. Optional GITHUB_TOKEN
lifts GitHub's 60-requests-an-hour limit; the script makes about 60 GitHub requests, so set it.

Usage: python3 check_langchain_alternatives.py [--as-of 2026-10-18T18:30:00Z] > out.json
"""
import datetime
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
HERE = os.path.dirname(os.path.abspath(__file__))
AS_OF = "2026-10-18T18:30:00Z"
if "--as-of" in sys.argv:
    AS_OF = sys.argv[sys.argv.index("--as-of") + 1]


def parse(ts):
    return datetime.datetime.strptime(ts[:19] + "Z", "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)


CUT = parse(AS_OF)
STABLE = re.compile(r"^\d+(\.\d+)*$")


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
            "downloads_last_month": json.loads(stats)["data"]["last_month"] if st2 == 200 else None}


def npm(pkg):
    st, body = get("https://registry.npmjs.org/" + urllib.parse.quote(pkg, safe="@"))
    if st != 200:
        return {"error": st}
    d = json.loads(body)
    times = {v: t for v, t in d.get("time", {}).items() if STABLE.match(v) and parse(t) <= CUT}
    ordered = sorted((t, v) for v, t in times.items())
    t, v = ordered[-1]
    st2, dl = get("https://api.npmjs.org/downloads/point/last-month/" + urllib.parse.quote(pkg, safe="@"))
    return {"latest_stable": v, "uploaded": t[:10], "days_before_cutoff": (CUT - parse(t)).days,
            "versions_in_90_days": sum(1 for tt, _ in ordered if (CUT - parse(tt)).days < 90),
            "downloads_last_month": json.loads(dl)["downloads"] if st2 == 200 else None}


# ---- 1. What "leaving LangChain" leaves behind --------------------------------------------------
family = {pkg: pypi(pkg) for pkg in ("langchain", "langchain-core", "langgraph", "langchain-classic", "langchain-community")}
packaging = {
    "packages": {k: {"latest_stable": v.get("latest_stable"), "uploaded": v.get("uploaded"), "base_dependencies": v.get("base_dependencies")} for k, v in family.items()},
    "langchain_requires_langgraph": "langgraph" in (family["langchain"].get("base_dependencies") or []),
    "langchain_core_requires_langsmith_client": "langsmith" in (family["langchain-core"].get("base_dependencies") or []),
    "langgraph_requires_langchain_core": "langchain-core" in (family["langgraph"].get("base_dependencies") or []),
    "langchain_community_requires_langchain_classic": "langchain-classic" in (family["langchain-community"].get("base_dependencies") or []),
}

# ---- 2. Twelve alternatives and LangChain itself ----------------------------------------------------
# name, ecosystem, package, GitHub repo
PROJECTS = [("LangChain", "pypi", "langchain", "langchain-ai/langchain"), ("LlamaIndex", "pypi", "llama-index-core", "run-llama/llama_index"),
            ("Haystack", "pypi", "haystack-ai", "deepset-ai/haystack"), ("DSPy", "pypi", "dspy", "stanfordnlp/dspy"),
            ("Pydantic AI", "pypi", "pydantic-ai-slim", "pydantic/pydantic-ai"), ("OpenAI Agents SDK", "pypi", "openai-agents", "openai/openai-agents-python"),
            ("Agno", "pypi", "agno", "agno-agi/agno"), ("CrewAI", "pypi", "crewai", "crewAIInc/crewAI"),
            ("smolagents", "pypi", "smolagents", "huggingface/smolagents"), ("AutoGen", "pypi", "autogen-agentchat", "microsoft/autogen"),
            ("Semantic Kernel", "pypi", "semantic-kernel", "microsoft/semantic-kernel"), ("Microsoft Agent Framework", "pypi", "agent-framework", "microsoft/agent-framework"),
            ("Vercel AI SDK", "npm", "ai", "vercel/ai"), ("Mastra", "npm", "@mastra/core", "mastra-ai/mastra")]
STATUS = re.compile(r"[^.>|\n]*(?:maintenance mode|is deprecated|now deprecated|no longer (?:actively )?(?:maintained|supported)|"
                    r"successor|superseded|replaced by|archived)[^.\n]*\.?", re.I)


def row(name, eco, pkg, repo):
    out = {"name": name, "ecosystem": eco, "package": pkg, "repo": repo, "registry": pypi(pkg) if eco == "pypi" else npm(pkg)}
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
    }
    if name == "LangChain":
        out["github"]["advisory_list"] = [{"id": a["ghsa_id"], "cve": a.get("cve_id"), "severity": a.get("severity"), "published": a["published_at"][:10],
                                          "summary": (a.get("summary") or "")[:140]} for a in sorted(advs, key=lambda a: a["published_at"], reverse=True)[:8]]
    return out


rows = [row(*p) for p in PROJECTS]
by = {r["name"]: r for r in rows}

# ---- 3. Claims in Google's AI Overview ------------------------------------------------------------
aio = open(os.path.join(HERE, "google-ai-overview-langchain-alternatives-2026-10-18.md"), encoding="utf-8").read()
ag = by["AutoGen"]["github"]
sk = by["Semantic Kernel"]["github"]
claims = {
    "overview_recommends_autogen": "AutoGen" in aio,
    "overview_mentions_maintenance_mode": bool(re.search(r"maintenance mode|deprecat", aio, re.I)),
    "autogen_readme_status_sentences": ag.get("readme_status_sentences"),
    "overview_recommends_semantic_kernel": "Semantic Kernel" in aio,
    "semantic_kernel_readme_status_sentences": sk.get("readme_status_sentences"),
    "overview_mentions_langgraph": "LangGraph" in aio,
    "overview_says_langchain_depends_on_anything": bool(re.search(r"depends on|built on LangGraph", aio, re.I)),
}

json.dump({"as_of": AS_OF, "langchain_packaging": packaging, "projects": rows, "claims_checked": claims}, sys.stdout, indent=2, sort_keys=True)
sys.stdout.write("\n")
