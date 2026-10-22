#!/usr/bin/env python3
"""Read public records about Braintrust and ten open-source alternatives, print one JSON document.

Standard library only, no account, nothing billed, nothing installed or run, no model called. Reads:
  - Braintrust's own pages: its pricing page, its self-hosting documentation, the title and text of its "Braintrust alternatives" article, and the
    licences of the repositories in its GitHub organisation
  - the licence file at the root of the ten alternatives (first lines, and any line naming a carve-out or a non-OSI licence)
  - GitHub's API for ten repositories: licence, archived flag, canonical name, last commit, latest stable release, releases in the last 90 days,
    published security advisories, README sentences about ownership or maintenance
  - PyPI and npm for each package: latest stable version, upload date, versions in 90 days
  - the Langfuse and ClickHouse announcements of the January 2026 acquisition
  - google-ai-overview-braintrust-alternatives-2026-10-21.md, saved next to this script, to check its claims

Dates use a fixed cut-off (--as-of 2026-10-21T19:30:00Z). Pages and READMEs are read live. Optional GITHUB_TOKEN lifts GitHub's 60-requests-an-hour limit;
the script makes about 70 GitHub requests, so set it.

Usage: python3 check_braintrust_alternatives.py [--as-of 2026-10-21T19:30:00Z] > out.json
"""
import datetime
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
HERE = os.path.dirname(os.path.abspath(__file__))
AS_OF = "2026-10-21T19:30:00Z"
if "--as-of" in sys.argv:
    AS_OF = sys.argv[sys.argv.index("--as-of") + 1]


def parse(ts):
    return datetime.datetime.strptime(ts[:19] + "Z", "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)


CUT = parse(AS_OF)


def get(url, headers=None, timeout=40):
    h = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
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


def find(pattern, text, group=0):
    m = re.search(pattern, text, re.I)
    return m.group(group) if m else None


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


# ---- 1. Braintrust's own pages -------------------------------------------------------------------------
pricing = text_of(get("https://www.braintrust.dev/pricing")[1])
selfhost = text_of(get("https://www.braintrust.dev/docs/guides/self-hosting")[1])
article_html = get("https://www.braintrust.dev/articles/braintrust-alternatives")[1]
article = text_of(article_html)
org = gh("/orgs/braintrustdata/repos?per_page=100&sort=pushed")
NAMED = ("braintrust-sdk-python", "braintrust-sdk-javascript", "braintrust-sdk-go", "autoevals", "braintrust-proxy", "helm", "terraform-aws-braintrust-data-plane")
braintrust = {
    "pricing_page": {
        "starter": find(r"(Starter For everyone \$0 / month \$10 credits \+ tok rates 1 GB processed data \+ \$4/GB 10k scores \+ \$2\.50/1k 14-day retention)", pricing, 1),
        "pro": find(r"(Pro For AI native teams \$249 / month \$100 credits \+ tok rates 5 GB processed data \+ \$3/GB 50k scores \+ \$1\.50/1k 30-day retention \+ \$0\.50/GB/mo)", pricing, 1),
        "enterprise": find(r"(Enterprise For teams at scale Custom pricing[^.]*?(?:on-prem or hosted deployment[^.]*?data))", pricing, 1),
        "no_credit_card_for_starter": "No credit card required" in pricing,
    },
    "self_hosting_docs": {
        "offers_self_hosted_deployment_separating_data_from_platform": "Braintrust offers a self-hosted deployment option that separates data storage from platform management" in selfhost,
        "control_plane_hosted_by_braintrust": "Braintrust continues to host the control plane" in selfhost,
        "data_plane_stores_sensitive_data": "The data plane stores all sensitive data" in selfhost,
        "mentions_byoc": "BYOC" in selfhost,
    },
    "own_alternatives_article": {
        "title": find(r"(Braintrust alternatives: What to consider \(and why there.s no true substitute\))", article, 1),
        "times_it_says_Braintrust": article.count("Braintrust"),
        "says_langfuse_is_mit_licensed": "Langfuse: An open-source (MIT licensed)" in article,
        "says_langfuse_you_build_the_ci_cd_layer": "you build the CI/CD and orchestration layer yourself" in article,
    },
    "github_org_repositories": {r["name"]: {"licence_spdx": (r.get("license") or {}).get("spdx_id"), "archived": r["archived"], "last_push": r["pushed_at"][:10]}
                                for r in (org if isinstance(org, list) else []) if r["name"] in NAMED},
}

# ---- 2. Licence files and README status lines ---------------------------------------------------------------
REPOS = [("Langfuse", "langfuse/langfuse", "langfuse", None, r"^v\d+\.\d+\.\d+$"),
         ("Arize Phoenix", "Arize-ai/phoenix", "arize-phoenix", None, r"^arize-phoenix-v\d+\.\d+\.\d+$"),
         ("Opik", "comet-ml/opik", "opik", None, r"^\d+\.\d+\.\d+$"),
         ("MLflow", "mlflow/mlflow", "mlflow", None, r"^v\d+\.\d+\.\d+$"),
         ("W&B Weave", "wandb/weave", "weave", None, r"^v?\d+\.\d+\.\d+$"),
         ("LangWatch", "langwatch/langwatch", "langwatch", None, r"^(?:[A-Za-z\-]+-)?v?\d+\.\d+\.\d+$"),
         ("Laminar", "lmnr-ai/lmnr", "lmnr", None, r"^v?\d+\.\d+\.\d+$"),
         ("DeepEval", "confident-ai/deepeval", "deepeval", None, r"^v?\d+\.\d+\.\d+$"),
         ("Promptfoo", "promptfoo/promptfoo", None, "promptfoo", r"^v?\d+\.\d+\.\d+$"),
         ("Ragas", "explodinggradients/ragas", "ragas", None, r"^v?\d+\.\d+\.\d+$")]
STATUS = re.compile(r"[^.>|\n]*(?:is now part of [A-Z][A-Za-z]+|joined [A-Z][A-Za-z]+|acquired by|maintenance mode|is deprecated|now deprecated|no longer (?:actively )?(?:maintained|supported)|archived|moved to)[^.\n]*\.?", re.I)


def pypi_row(pkg):
    st, body = get(f"https://pypi.org/pypi/{pkg}/json")
    if st != 200:
        return {"package": pkg, "error": st}
    rels = json.loads(body).get("releases", {})
    stable = sorted((files[0]["upload_time_iso_8601"], v) for v, files in rels.items()
                    if files and re.fullmatch(r"\d+(\.\d+)*", v) and parse(files[0]["upload_time_iso_8601"]) <= CUT)
    if not stable:
        return {"package": pkg, "error": "no stable release before cut-off"}
    t, v = stable[-1]
    return {"package": pkg, "registry": "pypi", "latest_stable": v, "uploaded": t[:10], "days_before_cutoff": (CUT - parse(t)).days,
            "versions_in_90_days": sum(1 for tt, _ in stable if (CUT - parse(tt)).days < 90)}


def npm_row(pkg):
    st, body = get("https://registry.npmjs.org/" + urllib.parse.quote(pkg, safe="@"))
    if st != 200:
        return {"package": pkg, "error": st}
    d = json.loads(body)
    times = sorted((t, v) for v, t in d.get("time", {}).items() if re.fullmatch(r"\d+(\.\d+)*", v) and parse(t) <= CUT)
    t, v = times[-1]
    return {"package": pkg, "registry": "npm", "latest_stable": v, "uploaded": t[:10], "days_before_cutoff": (CUT - parse(t)).days,
            "versions_in_90_days": sum(1 for tt, _ in times if (CUT - parse(tt)).days < 90)}


def repo_row(name, repo, pypi_pkg, npm_pkg, tag_re):
    meta = gh("/repos/" + repo)
    if "error" in meta:
        return {"name": name, "repo": repo, "error": meta["error"]}
    out = {"name": name, "repo": repo, "canonical_repo": meta["full_name"], "licence_spdx": (meta.get("license") or {}).get("spdx_id"), "archived": meta["archived"],
           "github_description": (meta.get("description") or "")[:160]}
    lic = gh(f"/repos/{meta['full_name']}/contents/LICENSE", raw=True)
    lines = [l.strip() for l in (lic or "").splitlines() if l.strip()]
    out["licence_file"] = {"found_at_repository_root": bool(lines), "says_mit_expat_outside_carve_out": 'available under the "MIT Expat" license' in (lic or ""), "first_line": lines[0][:100] if lines else None, "copyright_line": next((l[:100] for l in lines if l.lower().startswith("copyright")), None),
                           "has_ee_carve_out": any('"ee/"' in l or "ee/" in l and "licen" in l.lower() for l in lines),
                           "names_elastic_licence": any("Elastic License" in l for l in lines), "names_apache_or_mit_first": bool(lines and re.search(r"Apache License|MIT License", lines[0])),
                           "file_says_mit_license": "MIT License" in (lic or "") or "MIT license" in (lic or ""), "file_says_apache_license": "Apache License" in (lic or ""),
                           "carve_out_line": next((l[:200] for l in lines if "ee/" in l), None)}
    commit = gh(f"/repos/{repo}/commits?per_page=1&until={AS_OF}")
    out["last_commit_before_cutoff"] = commit[0]["commit"]["committer"]["date"][:10] if isinstance(commit, list) and commit else None
    rels = [r for r in gh_pages(f"/repos/{repo}/releases") if isinstance(r, dict) and not r.get("draft") and r.get("published_at") and parse(r["published_at"]) <= CUT]
    stable = sorted((r for r in rels if not r.get("prerelease") and re.search(tag_re, r["tag_name"])
                     and not re.search(r"nightly|alpha|beta|rc|dev|preview|canary", r["tag_name"], re.I)), key=lambda r: r["published_at"])
    out["latest_stable_release"] = ({"tag": stable[-1]["tag_name"], "date": stable[-1]["published_at"][:10], "days_before_cutoff": (CUT - parse(stable[-1]["published_at"])).days}
                                    if stable else None)
    out["stable_releases_in_90_days"] = sum(1 for r in stable if (CUT - parse(r["published_at"])).days < 90)
    advs = [a for a in gh_pages(f"/repos/{repo}/security-advisories") if isinstance(a, dict) and a.get("published_at") and parse(a["published_at"]) <= CUT]
    out["published_advisories"] = {"total": len(advs), "last_12_months": sum(1 for a in advs if (CUT - parse(a["published_at"])).days < 365),
                                   "by_severity": {s: sum(1 for a in advs if (a.get("severity") or "unknown") == s) for s in sorted({a.get("severity") or "unknown" for a in advs})},
                                   "latest": max((a["published_at"][:10] for a in advs), default=None)}
    readme = re.sub(r"\s+", " ", gh(f"/repos/{repo}/readme", raw=True))
    out["readme_status_sentences"] = [s.strip()[:200] for s in STATUS.findall(readme)][:3]
    out["registry"] = pypi_row(pypi_pkg) if pypi_pkg else (npm_row(npm_pkg) if npm_pkg else None)
    return out


rows = [repo_row(*r) for r in REPOS]
by = {r["name"]: r for r in rows}

# ---- 3. The Langfuse acquisition ---------------------------------------------------------------------------------
ch = text_of(get("https://clickhouse.com/blog/clickhouse-acquires-langfuse-open-source-llm-observability")[1])
lf = text_of(get("https://langfuse.com/blog/joining-clickhouse")[1])
acquisition = {"clickhouse_post_date": find(r"((?:Jan|Feb|Mar) \d{1,2}, 2026) · \d+ minutes read", ch, 1), "clickhouse_says": find(r"(ClickHouse has acquired Langfuse)", ch, 1),
               "langfuse_says_open_source_and_self_hostable": bool(re.search(r"Langfuse stays open source and self.hostable", lf)),
               "langfuse_says_no_planned_licence_change": "There are no planned changes to licensing" in lf}

# ---- 3b. The Promptfoo announcement --------------------------------------------------------------------------------
pf_blog = text_of(get("https://www.promptfoo.dev/blog/promptfoo-joining-openai/")[1])
promptfoo = {"url": "https://www.promptfoo.dev/blog/promptfoo-joining-openai/", "date": find(r"((?:January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, 2026)", pf_blog, 1),
             "says_agreed_to_be_acquired_by_openai": "Promptfoo has agreed to be acquired by OpenAI" in pf_blog,
             "says_will_remain_open_source": "Promptfoo will remain open source and we will continue to serve users and customers" in pf_blog,
             "says_will_maintain_open_source_suite": "We will continue to maintain the open-source suite as a best-in-class red teaming, static scanning, and evals tool for any AI model or application" in pf_blog,
             "says_closing_subject_to_customary_conditions": "The closing of the acquisition is subject to customary closing conditions" in pf_blog}

# ---- 4. Google's AI Overview ------------------------------------------------------------------------------------------
aio = open(os.path.join(HERE, "google-ai-overview-braintrust-alternatives-2026-10-21.md"), encoding="utf-8").read()
phx = by["Arize Phoenix"]
claims = {
    "overview_first_citation_is_braintrust_dev_alternatives_article": "braintrust.dev/articles/braintrust-alternatives" in aio,
    "braintrust_dev_links_in_overview": len(re.findall(r"braintrust\.dev", aio)),
    "overview_says_phoenix_apache_2_0": bool(re.search(r"Arize Phoenix\*\* \| Open Source \(Apache 2\.0\)", aio)),
    "phoenix_github_licence_spdx": phx.get("licence_spdx"), "phoenix_licence_file_first_line": phx.get("licence_file", {}).get("first_line"),
    "phoenix_licence_file_names_elastic": phx.get("licence_file", {}).get("names_elastic_licence"),
    "overview_says_langfuse_mit_licensed": "MIT-licensed" in aio or "Open Source (MIT)" in aio, "langfuse_licence_file_has_ee_carve_out": by["Langfuse"].get("licence_file", {}).get("has_ee_carve_out"),
    "overview_mentions_clickhouse_as_ownership": bool(re.search(r"acquired|owned by ClickHouse|ClickHouse (?:owns|acquisition)", aio)),
    "overview_says_opik_apache_2_0": "Apache 2.0 open-source platform" in aio, "opik_github_licence_spdx": by["Opik"].get("licence_spdx"),
    "overview_names_closed_products": [n for n in ("LangSmith", "Galileo", "Datadog") if n in aio],
    "overview_names_any_of_promptfoo_deepeval_weave_langwatch_ragas_mlflow_laminar": [n for n in ("Promptfoo", "DeepEval", "Weave", "LangWatch", "Ragas", "MLflow", "Laminar") if n in aio],
    "overview_mentions_openai_or_promptfoo_acquisition": bool(re.search(r"OpenAI", aio)),
    "promptfoo_readme_says_now_part_of_openai": any("now part of OpenAI" in s for s in by["Promptfoo"].get("readme_status_sentences", [])),
    "ragas_repo_resolves_to": by["Ragas"].get("canonical_repo"),
}

json.dump({"as_of": AS_OF, "braintrust": braintrust, "repositories": rows, "langfuse_acquisition": acquisition, "promptfoo_announcement": promptfoo, "claims_checked": claims}, sys.stdout, indent=2, sort_keys=True)
sys.stdout.write("\n")
