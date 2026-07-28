"""Verify how LangGraph 1.2.9 relates to LangChain, by inspecting the installed package.

No network calls, no model calls, no cost. Reads only the installed distribution in the
isolated LangGraph environment created for the 160-run benchmark.

The question this answers: is "LangChain vs LangGraph" a choice between two things, or a
choice between a library and something built on top of it?

Usage:
    python3 operations/verify_langchain_langgraph_coupling.py > <output>.json
"""

from __future__ import annotations

import collections
import hashlib
import json
import os
import re
import sys

SITE_PACKAGES = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ".venvs/langgraph/lib/python3.12/site-packages",
)

IMPORT_RE = re.compile(
    r"^\s*(?:from|import)\s+(langchain_core[\w.]*)(?:\s+import\s+([^\n#]+))?", re.M
)
REQUIRES_RE = re.compile(r"^Requires-Dist:\s*(.+)$", re.M)


def dist_version(name: str) -> str | None:
    prefix = f"{name}-"
    for entry in os.listdir(SITE_PACKAGES):
        if entry.startswith(prefix) and entry.endswith(".dist-info"):
            return entry[len(prefix) : -len(".dist-info")]
    return None


def metadata_requires(name: str) -> list[str]:
    prefix = f"{name}-"
    for entry in os.listdir(SITE_PACKAGES):
        if entry.startswith(prefix) and entry.endswith(".dist-info"):
            path = os.path.join(SITE_PACKAGES, entry, "METADATA")
            with open(path, encoding="utf-8") as handle:
                return REQUIRES_RE.findall(handle.read())
    return []


def scan_imports() -> dict:
    root = os.path.join(SITE_PACKAGES, "langgraph")
    total = 0
    importing = 0
    modules: collections.Counter = collections.Counter()
    symbols: collections.Counter = collections.Counter()
    digest = hashlib.sha256()

    for base, _dirs, files in os.walk(root):
        for filename in sorted(files):
            if not filename.endswith(".py"):
                continue
            total += 1
            path = os.path.join(base, filename)
            with open(path, encoding="utf-8", errors="replace") as handle:
                source = handle.read()
            digest.update(source.encode("utf-8", "replace"))
            hits = IMPORT_RE.findall(source)
            if not hits:
                continue
            importing += 1
            for module, names in hits:
                modules[module] += 1
                for name in (names or "").replace("(", "").replace(")", "").split(","):
                    name = name.strip().split(" as ")[0].strip()
                    if name and name != "*":
                        symbols[name] += 1

    return {
        "python_files": total,
        "files_importing_langchain_core": importing,
        "percent_importing": round(100 * importing / total, 1) if total else 0.0,
        "top_modules": modules.most_common(12),
        "top_symbols": symbols.most_common(15),
        "source_sha256": digest.hexdigest(),
    }


def main() -> None:
    langgraph_requires = metadata_requires("langgraph")
    core_pin = next(
        (r for r in langgraph_requires if r.startswith("langchain-core")), None
    )
    result = {
        "verified_utc": "2026-07-28",
        "environment": "isolated, offline, no model calls",
        "versions": {
            name: dist_version(name)
            for name in (
                "langgraph",
                "langchain_core",
                "langgraph_checkpoint",
                "langgraph_prebuilt",
                "langgraph_sdk",
            )
        },
        "langgraph_requires_dist": langgraph_requires,
        "langchain_core_pin": core_pin,
        "langgraph_can_be_installed_without_langchain_core": core_pin is None,
        "import_scan": scan_imports(),
    }
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
