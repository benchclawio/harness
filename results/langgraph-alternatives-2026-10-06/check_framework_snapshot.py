#!/usr/bin/env python3
"""Snapshot of release and maintenance metadata for LangGraph and its candidate alternatives.

Standard library only, no API key, nothing installed. One PyPI JSON request and one
unauthenticated GitHub REST request per project, sequential, no retries. Prints one JSON
document. This is metadata, not a measurement of how any framework behaves.
"""
import datetime
import json
import re
import sys
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (benchclaw framework snapshot)", "Accept": "application/json"}
TODAY = datetime.date.today()
PROJECTS = [
    ("LangGraph", "langgraph", "langchain-ai/langgraph"),
    ("Pydantic AI", "pydantic-ai-slim", "pydantic/pydantic-ai"),
    ("OpenAI Agents SDK", "openai-agents", "openai/openai-agents-python"),
    ("CrewAI", "crewai", "crewAIInc/crewAI"),
    ("Google ADK", "google-adk", "google/adk-python"),
    ("LlamaIndex", "llama-index-core", "run-llama/llama_index"),
    ("smolagents", "smolagents", "huggingface/smolagents"),
    ("Agno", "agno", "agno-agi/agno"),
    ("Claude Agent SDK", "claude-agent-sdk", "anthropics/claude-agent-sdk-python"),
    ("Microsoft Agent Framework", "agent-framework", "microsoft/agent-framework"),
    ("AutoGen", "autogen-agentchat", "microsoft/autogen"),
    ("Semantic Kernel", "semantic-kernel", "microsoft/semantic-kernel"),
]


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return json.load(r)


def short_license(info):
    expr = info.get("license_expression")
    if expr:
        return expr
    cls = [c.split("::")[-1].strip() for c in info.get("classifiers", []) if c.startswith("License ::")]
    if cls:
        return cls[0]
    text = (info.get("license") or "").strip()
    return text.splitlines()[0][:60] if text else None


def get_text(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA["User-Agent"]}), timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def is_pre(v):
    return bool(re.search(r"(a|b|rc|dev|post)\d*$|\.dev|rc", v)) and not re.fullmatch(r"\d+(\.\d+)*", v)


def days(d):
    return (TODAY - datetime.date.fromisoformat(d)).days


out = []
for name, pkg, repo in PROJECTS:
    row = {"name": name, "package": pkg, "repo": repo}
    try:
        p = get(f"https://pypi.org/pypi/{pkg}/json")
        info = p["info"]
        stable = {}
        for v, files in p["releases"].items():
            if files and not is_pre(v):
                stable[v] = min(f["upload_time"][:10] for f in files)
        latest = info["version"]
        req = [r for r in (info.get("requires_dist") or []) if "extra ==" not in r]
        row.update({
            "latest": latest, "latest_released": stable.get(latest),
            "days_since_latest": days(stable[latest]) if latest in stable else None,
            "stable_releases_last_90_days": sum(1 for d in stable.values() if days(d) <= 90),
            "first_stable_release": min(stable.values()) if stable else None,
            "license": short_license(info),
            "requires_python": info.get("requires_python"),
            "required_dependencies": len(req),
        })
    except Exception as e:
        row["pypi_error"] = str(e)
    try:
        g = get(f"https://api.github.com/repos/{repo}")
        row.update({"github_archived": g["archived"], "github_pushed_at": g["pushed_at"][:10],
                    "github_license": (g.get("license") or {}).get("spdx_id")})
    except Exception as e:
        row["github_error"] = str(e)
    try:
        readme = get_text(f"https://raw.githubusercontent.com/{repo}/HEAD/README.md")
        row["readme_says_maintenance_mode"] = bool(re.search(r"(?i)maintenance mode", readme))
        row["readme_mentions_microsoft_agent_framework"] = "Microsoft Agent Framework" in readme
        row["readme_calls_itself_successor"] = bool(re.search(r"(?i)successor to (AutoGen|Semantic Kernel)", readme))
    except Exception as e:
        row["readme_error"] = str(e)
    out.append(row)

json.dump({"read_on": TODAY.isoformat(), "projects": out}, sys.stdout, indent=2)
print()
