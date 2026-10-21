#!/usr/bin/env python3
"""Read public records about the Agent2Agent (A2A) protocol, print one JSON document.

Standard library only, no account, nothing billed, no package installed or run, no agent called. Reads:
  - the A2A specification site (a2a-protocol.org): released versions, transport bindings, breaking-change notes, the governance announcement
  - GitHub for the specification repository, the SDK repositories, and IBM's Agent Communication Protocol repository:
    licence, archived flag, creation date, last commit, latest stable release, releases in the last 90 days, published security advisories
  - PyPI and npm for the Python and JavaScript SDKs: version, date, downloads, declared extras
  - PyPI metadata of 14 agent frameworks, to see which declare an A2A extra or dependency (never installed)
  - google-ai-overview-a2a-protocol-2026-10-21.md, saved next to this script, to check its claims

Dates use a fixed cut-off (--as-of 2026-10-21T19:00:00Z). Download counts are the trailing month at read time. The specification site and the
announcement are read live. Optional GITHUB_TOKEN lifts GitHub's 60-requests-an-hour limit; the script makes about 50 GitHub requests, so set it.

Usage: python3 check_a2a_protocol.py [--as-of 2026-10-21T19:00:00Z] > out.json
"""
import datetime
import html
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
AS_OF = "2026-10-21T19:00:00Z"
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


def pypi(pkg, with_downloads=False):
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
    requires = info.get("requires_dist") or []
    out = {"latest_stable": v, "uploaded": t[:10], "days_before_cutoff": (CUT - parse(t)).days,
           "versions_in_90_days": sum(1 for tt, _ in stable if (CUT - parse(tt)).days < 90),
           "extras": sorted(info.get("provides_extra") or []), "requires_python": info.get("requires_python"),
           "mentions_a2a": sorted({r.split(";")[0].strip() for r in requires if "a2a" in r.lower()}),
           "extras_mentioning_a2a": sorted(e for e in (info.get("provides_extra") or []) if "a2a" in e.lower())}
    if with_downloads:
        time.sleep(1)
        st2, stats = get(f"https://pypistats.org/api/packages/{pkg}/recent")
        out["downloads_last_month"] = json.loads(stats)["data"]["last_month"] if st2 == 200 else None
    return out


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


STATUS = re.compile(r"[^.>|\n]*(?:merg|archived|no longer (?:actively )?(?:maintained|supported)|superseded|replaced by|joins?|A2A)[^.\n]*\.?", re.I)


def repo_row(name, repo, tag_re=r"^v?\d+\.\d+\.\d+(\.Final)?$", readme_status=False):
    meta = gh("/repos/" + repo)
    if "error" in meta:
        return {"name": name, "repo": repo, "error": meta["error"]}
    out = {"name": name, "repo": repo, "canonical_repo": meta["full_name"], "licence_spdx": (meta.get("license") or {}).get("spdx_id"),
           "archived": meta["archived"], "created": meta["created_at"][:10]}
    commit = gh(f"/repos/{repo}/commits?per_page=1&until={AS_OF}")
    out["last_commit_before_cutoff"] = commit[0]["commit"]["committer"]["date"][:10] if isinstance(commit, list) and commit else None
    releases = [r for r in gh_pages(f"/repos/{repo}/releases") if isinstance(r, dict) and not r.get("draft") and r.get("published_at") and parse(r["published_at"]) <= CUT]
    stable = sorted((r for r in releases if not r.get("prerelease") and re.search(tag_re, r["tag_name"])), key=lambda r: r["published_at"])
    out["latest_stable_release"] = ({"tag": stable[-1]["tag_name"], "date": stable[-1]["published_at"][:10], "days_before_cutoff": (CUT - parse(stable[-1]["published_at"])).days}
                                    if stable else None)
    out["stable_releases_in_90_days"] = sum(1 for r in stable if (CUT - parse(r["published_at"])).days < 90)
    out["recent_stable_releases"] = [{"tag": r["tag_name"], "date": r["published_at"][:10]} for r in reversed(stable[-4:])]
    pre = sorted((r for r in releases if r.get("prerelease") and re.search(r"\d+\.\d+\.\d+", r["tag_name"])), key=lambda r: r["published_at"])
    out["latest_prerelease"] = {"tag": pre[-1]["tag_name"], "date": pre[-1]["published_at"][:10]} if pre else None
    advs = [a for a in gh_pages(f"/repos/{repo}/security-advisories") if isinstance(a, dict) and a.get("published_at") and parse(a["published_at"]) <= CUT]
    out["published_advisories"] = {"total": len(advs), "by_severity": {s: sum(1 for a in advs if (a.get("severity") or "unknown") == s) for s in sorted({a.get("severity") or "unknown" for a in advs})},
                                   "latest": max((a["published_at"][:10] for a in advs), default=None),
                                   "list": [{"published": a["published_at"][:10], "severity": a.get("severity"), "summary": (a.get("summary") or "")[:130]}
                                            for a in sorted(advs, key=lambda a: a["published_at"], reverse=True)[:6]]}
    if readme_status:
        readme = re.sub(r"\s+", " ", gh(f"/repos/{repo}/readme", raw=True))
        out["readme_status_sentences"] = [s.strip()[:240] for s in STATUS.findall(readme)][:5]
    return out


# ---- 1. The specification site and the governance announcement ----------------------------------
spec_html = get("https://a2a-protocol.org/latest/specification/")[1]
spec = text_of(spec_html)
news = text_of(get("https://a2a-protocol.org/latest/blog/2026/08/27/a-new-chapter-for-a2a-joining-the-agentic-ai-foundation/")[1])
whats_new = text_of(get("https://a2a-protocol.org/latest/whats-new-v1/")[1])
mcp_page = text_of(get("https://a2a-protocol.org/latest/topics/a2a-and-mcp/")[1])
m = re.search(r"Latest Released Version (\d+\.\d+\.\d+) Previous Versions ((?:\d+\.\d+\.\d+ ?)+)", spec)
specification = {
    "latest_released_version": m.group(1) if m else None, "previous_versions": m.group(2).split() if m else None,
    "mentions": {k: len(re.findall(re.escape(k), spec)) for k in ("gRPC", "JSON-RPC", "HTTP+JSON", "Server-Sent Events", "OpenID", "OAuth", "mTLS", "JSON Web Signature")},
    "protocol_binding_sections": sorted(set(re.findall(r"\d+\. (?:JSON-RPC|gRPC|HTTP\+JSON/REST) Protocol Binding", spec))),
    "supports_multiple_bindings_sentence": "A2A protocol supports multiple protocol bindings" in spec,
    "page_footer_copyright": re.search(r"Copyright \d{4} [^.]*?\.", spec).group(0) if re.search(r"Copyright \d{4} [^.]*?\.", spec) else None,
    "says_v1_introduces_breaking_change": "Version 1.0 introduces a breaking change" in spec,
    "whats_new_lists_breaking_changes_section": "Breaking Changes Requiring Code Updates" in whats_new,
    "whats_new_says_part_type_unification_critical": "Part Type Unification (CRITICAL IMPACT)" in whats_new,
    "version_negotiation_header": "A2A-Version" in spec,
}
governance = {
    "announcement_date": re.search(r"(August \d+, 2026)", news).group(1) if re.search(r"(August \d+, 2026)", news) else None,
    "accepted_as_growth_stage_project_at_aaif": "accepted as a Growth Stage project at the Agentic AI Foundation" in news,
    "says_linux_foundation_directed_aaif": "Linux Foundation-directed AAIF" in news,
    "sibling_projects_named": [p for p in ("MCP", "goose", "AGENTS.md") if p in news],
    "says_backed_by_over_150_organizations": "over 150 organizations" in news,
    "frameworks_named_as_supporting": [f for f in ("LangGraph", "CrewAI", "Pydantic AI", "AG2", "IBM BeeAI") if f in news],
    "cloud_providers_named": [c for c in ("Google Cloud", "AWS Bedrock AgentCore Runtime", "Microsoft Azure AI Foundry") if c in news],
    "calls_mcp_vertical_and_a2a_horizontal": "vertical integration layer" in news and "horizontal protocol" in news,
}
a2a_vs_mcp_page = {"url": "https://a2a-protocol.org/latest/topics/a2a-and-mcp/", "http_text_chars": len(mcp_page),
                   "says_complementary": bool(re.search(r"complement", mcp_page, re.I))}

# ---- 2. Repositories --------------------------------------------------------------------------------------
repos = [repo_row("A2A specification", "a2aproject/A2A"), repo_row("Python SDK", "a2aproject/a2a-python"), repo_row("JavaScript SDK", "a2aproject/a2a-js"),
         repo_row("Java SDK", "a2aproject/a2a-java"), repo_row("Go SDK", "a2aproject/a2a-go"), repo_row(".NET SDK", "a2aproject/a2a-dotnet"),
         repo_row("IBM ACP (Agent Communication Protocol)", "i-am-bee/acp", readme_status=True),
         repo_row("google/A2A (old name)", "google/A2A")]

# ---- 3. SDK registries --------------------------------------------------------------------------------------
sdks = {"a2a-sdk (PyPI)": pypi("a2a-sdk", with_downloads=True), "@a2a-js/sdk (npm)": npm("@a2a-js/sdk")}

# ---- 4. Which frameworks declare an A2A extra or dependency ------------------------------------------------------
FRAMEWORKS = ["langgraph", "langgraph-api", "langchain", "crewai", "pydantic-ai-slim", "fasta2a", "google-adk", "ag2", "beeai-framework", "agno",
              "strands-agents", "semantic-kernel", "agent-framework", "openai-agents", "autogen-agentchat", "llama-index-core", "smolagents"]
frameworks = {p: pypi(p) for p in FRAMEWORKS}
declares = sorted(p for p, v in frameworks.items() if "error" not in v and (v["mentions_a2a"] or v["extras_mentioning_a2a"]))
fasta2a_json = json.loads(get("https://pypi.org/pypi/fasta2a/json")[1])["info"]
fasta2a_info = {"summary": fasta2a_json.get("summary"), "requires_dist": fasta2a_json.get("requires_dist"),
                "depends_on_a2a_sdk": any("a2a-sdk" in r for r in (fasta2a_json.get("requires_dist") or [])),
                "pydantic_ai_extra_requires": [r for r in (fasta2a_json.get("requires_dist") or []) if "pydantic-ai" in r]}


def sdk_pin(p):
    """The a2a-sdk specifier a framework declares, and whether it can resolve to an a2a-sdk 1.x release."""
    specs = [re.search(r"a2a-sdk(?:\[[^\]]*\])?\s*([^;]*)", r).group(1).strip() for r in (frameworks[p].get("mentions_a2a") or []) if r.startswith("a2a-sdk")]
    if not specs:
        return None
    caps_below_1 = [bool(re.search(r"<\s*1(\.0)?\b|<\s*0\.|~=\s*0\.", s)) for s in specs]
    return {"specifiers": specs, "all_specifiers_cap_below_1_0": all(caps_below_1)}


sdk_pins = {p: sdk_pin(p) for p in declares}
announcement_vs_metadata = {n: {"package": p, "declares_a2a_in_metadata": p in declares, "a2a_entries": frameworks[p].get("mentions_a2a") if "error" not in frameworks[p] else None}
                            for n, p in (("LangGraph", "langgraph"), ("CrewAI", "crewai"), ("Pydantic AI", "pydantic-ai-slim"), ("AG2", "ag2"), ("IBM BeeAI", "beeai-framework"))}

# ---- 5. Claims in Google's AI Overview --------------------------------------------------------------------------------
aio = open(os.path.join(HERE, "google-ai-overview-a2a-protocol-2026-10-21.md"), encoding="utf-8").read()
spec_repo = repos[0]
claims = {
    "overview_says_introduced_by_google_april_2025": "Introduced by Google in April 2025" in aio,
    "spec_repo_created": spec_repo.get("created"), "old_repo_name_resolves_to": repos[-1].get("canonical_repo"),
    "overview_says_governed_by_linux_foundation": "governed by the Linux Foundation" in aio,
    "overview_names_agentic_ai_foundation": "Agentic AI Foundation" in aio,
    "overview_lists_transports": [t for t in ("HTTP(S)", "JSON-RPC 2.0", "Server-Sent Events", "JSON", "gRPC") if t in aio],
    "spec_mentions_grpc_count": specification["mentions"]["gRPC"],
    "overview_mentions_grpc": "gRPC" in aio,
    "overview_mentions_v1_or_version": bool(re.search(r"\b(v?1\.0|version)\b", aio, re.I)),
    "overview_mentions_breaking_changes": bool(re.search(r"breaking", aio, re.I)),
    "overview_says_security_uses_tls_jwt_oidc": all(t in aio for t in ("TLS", "JSON Web Tokens", "OpenID Connect")),
    "overview_says_a2a_and_mcp_complementary": "complementary" in aio,
    "overview_mentions_any_framework_by_name": [f for f in ("LangGraph", "CrewAI", "Pydantic AI", "Google ADK", "AG2", "BeeAI") if f in aio],
}

json.dump({"as_of": AS_OF, "specification": specification, "governance_announcement": governance, "a2a_and_mcp_page": a2a_vs_mcp_page,
           "repositories": repos, "sdk_registries": sdks, "frameworks_metadata": frameworks, "frameworks_declaring_a2a": declares,
           "a2a_sdk_pins_by_framework": sdk_pins, "fasta2a_package": fasta2a_info, "announcement_vs_metadata": announcement_vs_metadata, "claims_checked": claims},
          sys.stdout, indent=2, sort_keys=True)
sys.stdout.write("\n")
