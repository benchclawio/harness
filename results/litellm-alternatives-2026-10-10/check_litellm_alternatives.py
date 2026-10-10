#!/usr/bin/env python3
"""Read public records about LiteLLM and seven alternative gateways, print one JSON document.

Standard library only, no account, nothing is billed and no gateway is run or called. Reads:
  - LiteLLM's own incident notice (docs.litellm.ai) and PyPI's incident report (blog.pypi.org)
  - PyPI's JSON API for litellm (were the compromised releases removed?) and the OSV record PYSEC-2026-2
  - GitHub's API for eight repositories: licence, language, archived flag, last commit, latest stable
    release, releases in the last 90 days, and published security advisories
  - Palo Alto Networks' release on the Portkey acquisition, Bifrost's and MLflow's own comparison pages
  - google-ai-overview-litellm-alternatives-2026-10-10.md, saved next to this script

Dates use a fixed cut-off (--as-of 2026-10-10T16:00:00Z), so two runs agree even though LiteLLM ships
almost daily. Page text and advisories are read live. Optional GITHUB_TOKEN lifts GitHub's 60-requests-an-hour
limit; the script makes about 40 GitHub requests, so set it.

Usage: python3 check_litellm_alternatives.py [--as-of 2026-10-10T16:00:00Z] > out.json
"""
import datetime
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
HERE = os.path.dirname(os.path.abspath(__file__))
AS_OF = "2026-10-10T16:00:00Z"
if "--as-of" in sys.argv:
    AS_OF = sys.argv[sys.argv.index("--as-of") + 1]


def parse(ts):
    return datetime.datetime.strptime(ts[:19] + "Z", "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)


CUT = parse(AS_OF)


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


def gh(path):
    h = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        h["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    st, body = get("https://api.github.com" + path, h)
    return json.loads(body) if st == 200 else {"error": st}


def gh_pages(path, limit=5):
    out = []
    for page in range(1, limit + 1):
        sep = "&" if "?" in path else "?"
        batch = gh(f"{path}{sep}per_page=100&page={page}")
        if not isinstance(batch, list):
            return out if out else batch
        out += batch
        if len(batch) < 100:
            break
    return out


def find(pattern, text, group=0):
    m = re.search(pattern, text, re.I)
    return m.group(group) if m else None


# ---- 1. The March 2026 incident, from the two primary sources and PyPI's own data ------------------
lt = text_of(get("https://docs.litellm.ai/blog/security-update-march-2026")[1])
pt = text_of(get("https://blog.pypi.org/posts/2026-04-02-incident-report-litellm-telnyx-supply-chain-attack/")[1])
incident = {
    "litellm_notice": {
        "url": "https://docs.litellm.ai/blog/security-update-march-2026",
        "published": find(r"Published: ([A-Z][a-z]{2} \d{1,2}, \d{4})", lt, 1),
        "compromised_versions_named": sorted(set(re.findall(r"litellm==(1\.\d+\.\d+)", lt))),
        "live_window_says": find(r"live on March 24, 2026 from [^.]*?(?:minutes)[^.]*", lt),
        "docker_proxy_image_not_impacted": "official LiteLLM Proxy Docker image were not impacted" in lt,
        "clean_release_after_incident": find(r"new clean version of LiteLLM is now available \((v[\d.]+)\)", lt, 1),
        "says_forensics_by": "Mandiant" if "Mandiant" in lt else None,
    },
    "pypi_report": {
        "url": "https://blog.pypi.org/posts/2026-04-02-incident-report-litellm-telnyx-supply-chain-attack/",
        "downloads_during_window": find(r"downloaded over ([\d,.]+k?) times", pt, 1),
        "inbound_malware_reports": find(r"received (\d+) inbound reports", pt, 1),
        # The report prints two timelines in this order: litellm first, then telnyx. Keep litellm's.
        "upload_to_first_report": (re.findall(r"From upload to first report: ([\dhm ]+?)(?= First| From| Form|\s*\*|$)", pt) or [None])[0],
        "first_report_to_quarantine": (re.findall(r"First report to quarantine: ([\dhm ]+?)(?= From| Form|\s*\*|$)", pt) or [None])[0],
        "total_exposure_upload_to_quarantine": (re.findall(r"total exposure time\)\*{0,2}: ?\**([\dhm]+(?: [\dhm]+)?)", pt) or [None])[0],
        "timelines_printed": len(re.findall(r"total exposure time", pt)),
        "advisory_ids_named": sorted(set(re.findall(r"PYSEC-2026-\d+", pt))),
        "unpinned_installs_share_says": find(r"between \*{0,2}(~?\d+-\d+% of all installs)", pt, 1),
    },
}
st, body = get("https://pypi.org/pypi/litellm/json")
pypi = json.loads(body) if st == 200 else {}
rels = pypi.get("releases", {})


def release_row(v):
    files = rels.get(v) or []
    return {"present_on_pypi": bool(files), "uploaded": files[0]["upload_time_iso_8601"][:19] + "Z" if files else None,
            "yanked": any(f.get("yanked") for f in files) if files else None}


incident["pypi_json"] = {v: release_row(v) for v in ("1.82.6", "1.82.7", "1.82.8", "1.83.0")}
incident["pypi_json_status_for_removed_versions"] = {
    v: get(f"https://pypi.org/pypi/litellm/{v}/json")[0] for v in ("1.82.7", "1.82.8")}
stable = [(files[0]["upload_time_iso_8601"], v) for v, files in rels.items()
          if files and not re.search(r"[a-z]", v) and parse(files[0]["upload_time_iso_8601"]) <= CUT]
stable.sort()
incident["stable_releases_in_90_days_before_cutoff"] = sum(
    1 for t, _ in stable if (CUT - parse(t)).days < 90)
incident["latest_stable_before_cutoff"] = {"version": stable[-1][1], "uploaded": stable[-1][0][:10]} if stable else None
st, body = get("https://api.osv.dev/v1/vulns/PYSEC-2026-2")
osv = json.loads(body) if st == 200 else {}
incident["osv_PYSEC-2026-2"] = {
    "summary": osv.get("summary"), "published": (osv.get("published") or "")[:10], "aliases": osv.get("aliases"),
    "affected_versions": sorted(v for a in osv.get("affected", []) for v in a.get("versions", []))}
licence_text = get("https://raw.githubusercontent.com/BerriAI/litellm/main/LICENSE")[1]
incident["litellm_licence_file"] = {
    "first_line": licence_text.splitlines()[0] if licence_text else None,
    "enterprise_directory_carve_out": '"enterprise/" directory' in licence_text,
    "rest_is_mit": "MIT license" in licence_text}

# ---- 2. Eight repositories ----------------------------------------------------------------------
# name, repo, and the tag pattern of the main product. Bifrost tags about 15 packages per release day
# (core/, plugins/..., framework/); only its gateway series, transports/vX.Y.Z, is counted.
REPOS = [("LiteLLM", "BerriAI/litellm", r"^v\d+\.\d+\.\d+$"), ("Bifrost", "maximhq/bifrost", r"^transports/v\d+\.\d+\.\d+$"),
         ("MLflow (AI Gateway)", "mlflow/mlflow", r"^v\d+\.\d+\.\d+$"), ("Kong Gateway", "Kong/kong", r"^\d+\.\d+\.\d+$"),
         ("Envoy AI Gateway", "envoyproxy/ai-gateway", r"^v\d+\.\d+\.\d+$"), ("Portkey gateway", "Portkey-AI/gateway", r"^v\d+\.\d+\.\d+$"),
         ("Helicone", "Helicone/helicone", r"^v\d{4}\.\d{2}\.\d{2}"), ("TensorZero", "tensorzero/tensorzero", r"^\d{4}\.\d+\.\d+$")]


def repo_row(name, repo, tag_re):
    meta = gh("/repos/" + repo)
    if "error" in meta:
        return {"name": name, "repo": repo, "error": meta["error"]}
    out = {"name": name, "repo": repo, "canonical_repo": meta["full_name"], "licence_spdx": (meta.get("license") or {}).get("spdx_id"),
           "language": meta.get("language"), "archived": meta["archived"]}
    commit = gh(f"/repos/{repo}/commits?per_page=1&until={AS_OF}")
    out["last_commit_before_cutoff"] = commit[0]["commit"]["committer"]["date"][:10] if isinstance(commit, list) and commit else None
    releases = [r for r in gh_pages(f"/repos/{repo}/releases") if isinstance(r, dict) and not r.get("draft")
                and r.get("published_at") and parse(r["published_at"]) <= CUT]
    stable_rel = [r for r in releases if not r.get("prerelease") and re.search(tag_re, r["tag_name"])
                  and not re.search(r"nightly|alpha|beta|rc|dev|preview", r["tag_name"], re.I)]
    stable_rel.sort(key=lambda r: r["published_at"])
    out["latest_stable_release_before_cutoff"] = ({"tag": stable_rel[-1]["tag_name"], "date": stable_rel[-1]["published_at"][:10],
                                                    "days_before_cutoff": (CUT - parse(stable_rel[-1]["published_at"])).days}
                                                   if stable_rel else None)
    out["stable_releases_in_90_days"] = sum(1 for r in stable_rel if (CUT - parse(r["published_at"])).days < 90)
    advs = gh_pages(f"/repos/{repo}/security-advisories")
    if isinstance(advs, list):
        advs = [a for a in advs if a.get("published_at") and parse(a["published_at"]) <= CUT]
        sev = {}
        for a in advs:
            sev[a.get("severity") or "unknown"] = sev.get(a.get("severity") or "unknown", 0) + 1
        out["published_advisories"] = {"total": len(advs), "last_12_months": sum(1 for a in advs if (CUT - parse(a["published_at"])).days < 365),
                                       "by_severity": dict(sorted(sev.items())),
                                       "latest": max((a["published_at"][:10] for a in advs), default=None)}
    else:
        out["published_advisories"] = {"error": advs.get("error") if isinstance(advs, dict) else "unavailable"}
    return out


repos = [repo_row(n, r, t) for n, r, t in REPOS]
lit_adv = gh_pages("/repos/BerriAI/litellm/security-advisories")
lit_adv = [a for a in lit_adv if isinstance(a, dict) and a.get("published_at") and parse(a["published_at"]) <= CUT] if isinstance(lit_adv, list) else []
critical = sorted(((a["published_at"][:10], a["ghsa_id"], a["summary"]) for a in lit_adv if a.get("severity") == "critical"))

# ---- 3. Claims in Google's AI Overview and in vendors' own pages --------------------------------
aio = open(os.path.join(HERE, "google-ai-overview-litellm-alternatives-2026-10-10.md"), encoding="utf-8").read()
pan = text_of(get("https://www.paloaltonetworks.com/company/press/2026/palo-alto-networks-completes-acquisition-of-portkey-to-secure-ai-agents")[1])
bif = text_of(get("https://www.getmaxim.ai/bifrost/resources/litellm-alternative")[1])
mlf = text_of(get("https://mlflow.org/litellm-alternative/")[1])
by = {r["name"]: r for r in repos}
claims = {
    "ai_overview": {
        "says_bifrost_50x_lower_p99": "~50x lower P99" in aio,
        "bifrost_page_it_cites_contains_50x": bool(re.search(r"\b50\s?x\b", bif, re.I)),
        "says_bifrost_written_in_go": "Written in Go" in aio, "github_language_for_bifrost": by["Bifrost"].get("language"),
        "says_kong_apache_2_core": "Apache 2.0 core" in aio, "github_licence_for_kong": by["Kong Gateway"].get("licence_spdx"),
        "says_agent_router_formerly_envoy_ai_gateway": "Agent Router (formerly Envoy AI Gateway)" in aio,
        "github_resolves_envoyproxy_ai_gateway_to": by["Envoy AI Gateway"].get("canonical_repo"),
        "says_portkey_now_part_of_palo_alto": "Palo Alto Networks as Prisma AIRS" in aio,
        "palo_alto_release_says_closed_acquisition": "closed the acquisition of Portkey" in pan,
        "palo_alto_release_date": find(r"(May \d{1,2}, 2026) -- Palo Alto", pan, 1),
        "says_openrouter_5_5_pct_fee": "5.5%" in aio},
    "bifrost_page": {"gateway_overhead_claim": find(r"(\d+\s?µs Gateway Overhead At [\d,]+ RPS sustained)", bif, 1),
                     "provider_claim": find(r"(\d+\+? Models \d+\+? providers supported)", bif, 1)},
    "mlflow_page": {"p50_row": find(r"(P50 [\d.]+ ms [\d.]+ ms [\d.]+ ms [\d.]+ ms -?\d+%)", mlf, 1),
                    "p99_row": find(r"(P99 [\d.]+ ms [\d.]+ ms [\d.]+ ms [\d.]+ ms -?\d+%)", mlf, 1),
                    "test_conditions": find(r"(We benchmarked both gateways with a [^.]*?\))", mlf, 1),
                    "throughput_row": find(r"(Throughput [\d.]+ req/s [\d.]+ req/s \+?-?\d+%)", mlf, 1),
                    "table_header": find(r"(Metric MLflow LiteLLM[^%]{0,80}?Latency Overhead Latency Overhead)", mlf, 1),
                    "throughput_claim": find(r"(delivers \d+% higher throughput compared to LiteLLM)", mlf, 1),
                    "says_linux_foundation_governed": "Linux Foundation" in mlf,
                    "says_litellm_is_mit": "LiteLLM is open source under the MIT license" in mlf,
                    "mentions_march_2026_incident": "March 2026, LiteLLM experienced a supply chain incident" in mlf},
}

result = {
    "as_of": AS_OF,
    "incident": incident,
    "repositories": repos,
    "litellm_critical_advisories": [{"published": d, "id": i, "summary": s} for d, i, s in critical],
    "claims_checked": claims,
}
json.dump(result, sys.stdout, indent=2, sort_keys=True)
sys.stdout.write("\n")
