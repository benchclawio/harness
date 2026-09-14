"""Deterministic check: how many of Guardrails Hub's validators are installable from
plain PyPI, following the project's 2026-08-25 hard cutoff for `guardrails hub install`
and the private validator registry (github.com/guardrails-ai/guardrails/issues/1560).

Zero-dependency: standard library only, no API key, no pip install required to run it.

Usage: python3 check_guardrails_pypi_migration.py <slugs.txt> <out.json>
  slugs.txt: one Hub validator slug per line, as they appear in each validator's Hub URL
             (https://guardrailsai.com/hub/hub/validator/guardrails/<slug>). Collected by
             hand from https://guardrailsai.com/hub on 2026-09-14 (65 validators listed).
"""
import json
import sys
import time
from urllib.request import Request, urlopen

# Guardrails' migration issue documents this exact rename rule: "Each validator is now a
# standalone PyPI package named guardrails-ai-<name> (underscores become dashes)".
def package_name(slug: str) -> str:
    return "guardrails-ai-" + slug.replace("_", "-")


def check(slug: str, timeout: float = 15.0):
    pkg = package_name(slug)
    req = Request(f"https://pypi.org/pypi/{pkg}/json", headers={"User-Agent": "BenchClawResearch/1.0"})
    try:
        with urlopen(req, timeout=timeout) as response:
            data = json.load(response)
    except Exception as error:
        return {"slug": slug, "package": pkg, "found": False, "error": str(error)[:160]}
    version = data["info"]["version"]
    files = data["releases"].get(version, [])
    released = min((f["upload_time_iso_8601"][:10] for f in files), default=None)
    return {"slug": slug, "package": pkg, "found": True, "version": version, "released": released}


def main():
    slugs_path, out_path = sys.argv[1], sys.argv[2]
    slugs = [line.strip() for line in open(slugs_path) if line.strip()]
    results = []
    for slug in slugs:
        results.append(check(slug))
        time.sleep(0.1)  # be polite to PyPI; this is a one-shot 65-call sweep, not polling

    found = [r for r in results if r["found"]]
    missing = [r for r in results if not r["found"]]
    summary = {
        "checked_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "hub_url": "https://guardrailsai.com/hub",
        "validators_listed_on_hub": len(slugs),
        "found_on_pypi": len(found),
        "missing_from_pypi": [r["package"] for r in missing],
        "earliest_release": min((r["released"] for r in found if r["released"]), default=None),
        "latest_release": max((r["released"] for r in found if r["released"]), default=None),
        "results": results,
    }
    json.dump(summary, open(out_path, "w"), indent=2)
    print(f"{len(found)}/{len(slugs)} Hub validators found on PyPI")
    if missing:
        print("missing:", ", ".join(r["package"] for r in missing))
    print(f"release dates span {summary['earliest_release']} to {summary['latest_release']}")


if __name__ == "__main__":
    main()
