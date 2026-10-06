#!/usr/bin/env python3
"""Check the CrewAI dependency blocker and what each alternative's README says about multi-agent features.

Standard library only, no API key, nothing installed. PyPI JSON, the GitHub advisory API and raw
READMEs, one request each, sequential, no retries. Prints one JSON document. README word counts
show what a project says it does, not what it does.
"""
import datetime
import json
import re
import sys
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (benchclaw crewai check)", "Accept": "application/json"}


def get(url, text=False):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        body = r.read().decode("utf-8", "replace")
    return body if text else json.loads(body)


def stable(v):
    return bool(re.fullmatch(r"\d+(\.\d+)*", v))


crew = get("https://pypi.org/pypi/crewai/json")["info"]
req = crew.get("requires_dist") or []
core = [r for r in req if "extra ==" not in r]
chroma_core = [r for r in core if r.lower().startswith("chromadb")]
chroma_extra = [r for r in req if r.lower().startswith("chromadb") and "extra ==" in r]

chroma = get("https://pypi.org/pypi/chromadb/json")
cs = sorted(((min(f["upload_time"][:10] for f in fl), v) for v, fl in chroma["releases"].items() if fl and stable(v)))
adv = get("https://api.github.com/advisories/GHSA-f4j7-r4q5-qw2c")

readmes = []
for name, repo in [
    ("LangGraph", "langchain-ai/langgraph"), ("Microsoft Agent Framework", "microsoft/agent-framework"),
    ("Google ADK", "google/adk-python"), ("OpenAI Agents SDK", "openai/openai-agents-python"),
    ("Pydantic AI", "pydantic/pydantic-ai"), ("Agno", "agno-agi/agno"), ("AutoGen", "microsoft/autogen"),
    ("smolagents", "huggingface/smolagents"), ("CrewAI", "crewAIInc/crewAI"), ("OpenAI Swarm", "openai/swarm"),
]:
    row = {"name": name, "repo": repo}
    try:
        t = get(f"https://raw.githubusercontent.com/{repo}/HEAD/README.md", text=True)
        low = t.lower()
        row.update({"multi_agent": len(re.findall(r"multi[- ]agent", low)), "handoff": low.count("handoff") + low.count("hand-off"),
                    "team": len(re.findall(r"\bteams?\b", low)), "role": len(re.findall(r"\broles?\b", low)),
                    "readme_words": len(t.split())})
        if name == "OpenAI Swarm":
            row["says_replaced_by_agents_sdk"] = bool(re.search(r"(?i)replaced by .*openai agents sdk", t))
    except Exception as e:
        row["error"] = str(e)
    try:
        row["archived"] = get(f"https://api.github.com/repos/{repo}")["archived"]
    except Exception as e:
        row["archived_error"] = str(e)
    readmes.append(row)

json.dump({
    "read_on": datetime.date.today().isoformat(),
    "crewai": {"latest": crew["version"], "requires_python": crew.get("requires_python"),
               "direct_required_dependencies": len(core), "chromadb_core_requirement": chroma_core,
               "chromadb_in_extras": chroma_extra},
    "chromadb": {"latest": cs[-1][1], "latest_released": cs[-1][0], "last_five": cs[-5:]},
    "advisory": {"id": adv.get("ghsa_id"), "cve": adv.get("cve_id"), "severity": adv.get("severity"), "summary": adv.get("summary"),
                 "vulnerabilities": [{"package": v["package"]["name"], "vulnerable_range": v.get("vulnerable_version_range"),
                                      "first_patched": v.get("first_patched_version")} for v in adv.get("vulnerabilities", [])]},
    "readme_mentions": readmes,
}, sys.stdout, indent=2)
print()
