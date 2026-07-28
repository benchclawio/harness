"""Record the LangChain <-> LangGraph dependency direction from the PyPI release metadata.

Companion to verify_langchain_langgraph_coupling.py, which is offline-only. This one makes
read-only, unauthenticated, free requests to the public PyPI JSON API and records exactly
what the current releases declare.

Answers: in the versions shipping today, is "LangChain vs LangGraph" a choice at all?

Usage:
    python3 operations/verify_langchain_release_graph.py > <output>.json
"""

from __future__ import annotations

import json
import sys
import urllib.request

PACKAGES = ("langchain", "langchain-core", "langgraph", "langgraph-checkpoint")


def fetch(package: str) -> dict:
    url = f"https://pypi.org/pypi/{package}/json"
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.load(response)


def unconditional(requires: list[str] | None) -> list[str]:
    """Requirements with no environment marker - i.e. always installed."""
    return [r for r in (requires or []) if ";" not in r]


def main() -> None:
    out: dict = {"queried_utc": "2026-07-28", "source": "pypi.org JSON API (free, read-only)"}
    packages: dict = {}

    for name in PACKAGES:
        data = fetch(name)
        info = data["info"]
        files = data["releases"].get(info["version"], [])
        packages[name] = {
            "version": info["version"],
            "released": files[0]["upload_time"][:10] if files else None,
            "requires_python": info.get("requires_python"),
            "unconditional_requires": unconditional(info.get("requires_dist")),
        }

    langchain = packages["langchain"]["unconditional_requires"]
    langgraph = packages["langgraph"]["unconditional_requires"]

    out["packages"] = packages
    out["findings"] = {
        "langchain_requires_langgraph": any(r.startswith("langgraph") for r in langchain),
        "langchain_langgraph_pin": next(
            (r for r in langchain if r.startswith("langgraph")), None
        ),
        "langgraph_requires_langchain_umbrella": any(
            r.split()[0] == "langchain" for r in langgraph
        ),
        "langgraph_requires_langchain_core": any(
            r.startswith("langchain-core") for r in langgraph
        ),
        "langchain_unconditional_dependency_count": len(langchain),
        "installing_langchain_installs_langgraph": any(
            r.startswith("langgraph") for r in langchain
        ),
        "installing_langgraph_installs_langchain": any(
            r.split()[0] == "langchain" for r in langgraph
        ),
    }
    json.dump(out, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
