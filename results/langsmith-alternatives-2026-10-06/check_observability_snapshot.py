#!/usr/bin/env python3
"""Release, licence and OpenTelemetry-dependency snapshot for LangSmith and candidate alternatives.

Standard library only, no API key, nothing installed. One PyPI JSON request, one unauthenticated
GitHub REST request and one raw README request per project, sequential, no retries. Prints one JSON
document. This is metadata: it does not measure tracing quality, and a declared OpenTelemetry
dependency is a proxy for OpenTelemetry-based instrumentation, not proof of it.
"""
import datetime
import json
import re
import sys
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (benchclaw observability snapshot)", "Accept": "application/json"}
TODAY = datetime.date.today()
# (name, PyPI package, GitHub repo whose licence we report, what that repo is)
PROJECTS = [
    ("LangSmith (SDK)", "langsmith", "langchain-ai/langsmith-sdk", "client SDK; the platform is not in this repo"),
    ("Langfuse", "langfuse", "langfuse/langfuse", "platform and server"),
    ("Arize Phoenix", "arize-phoenix", "Arize-ai/phoenix", "platform and server"),
    ("MLflow", "mlflow", "mlflow/mlflow", "platform and server"),
    ("Opik", "opik", "comet-ml/opik", "platform and server"),
    ("Laminar", "lmnr", "lmnr-ai/lmnr", "platform and server"),
    ("OpenLLMetry", "traceloop-sdk", "traceloop/openllmetry", "instrumentation only"),
    ("Braintrust (SDK)", "braintrust", "braintrustdata/braintrust-sdk", "client SDK; the platform is not in this repo"),
    ("W&B Weave", "weave", "wandb/weave", "client library and tracing"),
    ("DeepEval", "deepeval", "confident-ai/deepeval", "evaluation library"),
]


def get(url, text=False):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        body = r.read().decode("utf-8", "replace")
    return body if text else json.loads(body)


def is_stable(v):
    return bool(re.fullmatch(r"\d+(\.\d+)*", v))


def short_license(info):
    if info.get("license_expression"):
        return info["license_expression"]
    cls = [c.split("::")[-1].strip() for c in info.get("classifiers", []) if c.startswith("License ::")]
    if cls:
        return cls[0]
    t = (info.get("license") or "").strip()
    return t.splitlines()[0][:60] if t else None


rows = []
for name, pkg, repo, repo_kind in PROJECTS:
    row = {"name": name, "package": pkg, "repo": repo, "repo_kind": repo_kind}
    try:
        p = get(f"https://pypi.org/pypi/{pkg}/json")
        info = p["info"]
        stable = {v: min(f["upload_time"][:10] for f in fl) for v, fl in p["releases"].items() if fl and is_stable(v)}
        latest = info["version"]
        req = [r for r in (info.get("requires_dist") or []) if "extra ==" not in r]
        row.update({
            "latest": latest, "latest_released": stable.get(latest),
            "days_since_latest": (TODAY - datetime.date.fromisoformat(stable[latest])).days if latest in stable else None,
            "releases_last_90_days": sum(1 for d in stable.values() if (TODAY - datetime.date.fromisoformat(d)).days <= 90),
            "first_non_prerelease": min(stable.values()) if stable else None,
            "pypi_license": short_license(info), "requires_python": info.get("requires_python"),
            "declares_opentelemetry_dependency": any(r.lower().startswith("opentelemetry") for r in req),
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
        t = get(f"https://raw.githubusercontent.com/{repo}/HEAD/README.md", text=True).lower()
        row["readme_mentions_self_host"] = len(re.findall(r"self[- ]?host", t))
        row["readme_mentions_opentelemetry"] = len(re.findall(r"opentelemetry|otel", t))
    except Exception as e:
        row["readme_error"] = str(e)
    rows.append(row)

json.dump({"read_on": TODAY.isoformat(), "projects": rows}, sys.stdout, indent=2)
print()
