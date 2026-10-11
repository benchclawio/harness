#!/usr/bin/env python3
"""Static read of REA (github.com/morluto/rea, npm package rea-agents), print one JSON document.

Standard library only. REA is NOT installed, imported or run, and nothing is analysed with it: the
script only reads public records. Reads:
  - GitHub API: repository metadata, releases, the files install.sh, package.json, SECURITY.md,
    README.md, docs/installation.md and .gitmodules at the latest release tag, and the five
    submodule repositories' licences
  - the npm registry record for rea-agents (versions, publish times, install hooks, dependencies,
    provenance attestation)
  - 17 U.S.C. 1201(f) from Cornell's Legal Information Institute

Dates use a fixed cut-off (--as-of 2026-10-11T18:00:00Z). Star and fork counts move every minute, so they
are not part of the JSON; the article quotes them with their read time. Optional GITHUB_TOKEN lifts GitHub's
60-requests-an-hour limit (the script makes about 25 requests).

Usage: python3 check_rea.py [--as-of 2026-10-11T18:00:00Z] > out.json
"""
import base64
import datetime
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
AS_OF = "2026-10-11T18:00:00Z"
if "--as-of" in sys.argv:
    AS_OF = sys.argv[sys.argv.index("--as-of") + 1]


def parse(ts):
    return datetime.datetime.strptime(ts[:19] + "Z", "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)


CUT = parse(AS_OF)


def get(url, headers=None):
    h = {"User-Agent": UA}
    h.update(headers or {})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=40) as r:
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
        return {"error": st} if not raw else ""
    return body if raw else json.loads(body)


REPO = "morluto/rea"
meta = gh("/repos/" + REPO)
releases = [r for r in gh(f"/repos/{REPO}/releases?per_page=100") if r.get("published_at") and parse(r["published_at"]) <= CUT and not r.get("draft")]
releases.sort(key=lambda r: r["published_at"])
series = [r for r in releases if re.match(r"^rea-agents-\d+\.\d+\.\d+$", r["tag_name"])]
latest_tag = series[-1]["tag_name"]
repo = {
    "full_name": meta["full_name"], "licence_spdx": (meta.get("license") or {}).get("spdx_id"), "language": meta.get("language"),
    "created": meta["created_at"][:10], "archived": meta["archived"], "owner_type": meta["owner"]["type"],
    "latest_release": {"tag": latest_tag, "date": series[-1]["published_at"][:10]},
    "releases_last_7_days": sum(1 for r in series if (CUT - parse(r["published_at"])).days < 7),
    "release_tags_last_8": [(r["tag_name"].replace("rea-agents-", ""), r["published_at"][:10]) for r in series[-8:]],
}


def file_at(path):
    return gh(f"/repos/{REPO}/contents/{path}?ref={latest_tag}", raw=True)


install_sh, security, readme, install_doc, gitmodules, pkg_json = (
    file_at("install.sh"), file_at("SECURITY.md"), file_at("README.md"), file_at("docs/installation.md"),
    file_at(".gitmodules"), file_at("package.json"))
pkg = json.loads(pkg_json) if pkg_json else {}
flat = lambda t: re.sub(r"\s+", " ", t)
security_f, install_doc_f, readme_f = flat(security), flat(install_doc), flat(readme)

# ---- npm registry record ------------------------------------------------------------------------
st, body = get("https://registry.npmjs.org/rea-agents")
npm = json.loads(body) if st == 200 else {}
times = npm.get("time", {})
published = sorted((t, v) for v, t in times.items() if v not in ("created", "modified") and parse(t) <= CUT)
latest_v = published[-1][1]
manifest = npm["versions"][latest_v]
deps = manifest.get("dependencies", {})
npm_row = {
    "package_created": times.get("created", "")[:10], "versions_by_cutoff": len(published), "latest": latest_v,
    "publish_dates_last_8": [(v, t[:16].replace("T", " ")) for t, v in published[-8:]],
    "versions_published_last_7_days": sum(1 for t, v in published if (CUT - parse(t)).days < 7),
    "maintainers": len(npm.get("maintainers", [])), "licence": manifest.get("license"),
    "has_install_script": bool(manifest.get("hasInstallScript")),
    "install_hooks_in_manifest": [k for k in (manifest.get("scripts") or {}) if k in ("preinstall", "install", "postinstall")],
    "dependency_count": len(deps), "dependencies_exact_pinned": all(re.match(r"^\d", v) for v in deps.values()),
    "unpacked_size_mb": round(manifest["dist"].get("unpackedSize", 0) / 1e6, 1), "file_count": manifest["dist"].get("fileCount"),
    "provenance_predicate": (manifest["dist"].get("attestations") or {}).get("provenance", {}).get("predicateType"),
    "repository_matches": "morluto/rea" in json.dumps(manifest.get("repository")),
    "bin_names": sorted((manifest.get("bin") or {}).keys()),
}

# ---- install.sh, SECURITY.md, setup behaviour, README claims ------------------------------------
hosts = sorted(set(re.findall(r"https?://([A-Za-z0-9.-]+)", install_sh)))
installer = {
    "hosts_contacted": [h for h in hosts if "nodejs.org" not in h],
    "mentions_sudo": len(re.findall(r"\bsudo\b", install_sh)), "pipes_download_to_shell": bool(re.search(r"curl[^\n|]*\|\s*(ba)?sh", install_sh)),
    "strict_mode": "set -euo pipefail" in install_sh,
    "installs_with": re.search(r"install_args=\(([^)]*)\)", install_sh).group(1) if re.search(r"install_args=\(([^)]*)\)", install_sh) else None,
    "linux_prefix_is_home_local": "--prefix \"$HOME/.local\"" in install_sh,
    "says_it_installs_only_the_cli": "Installs only the REA CLI" in install_sh,
    "runs_setup_when_terminal_available": "rea setup" in install_sh or '"$install_bin" setup' in install_sh,
}
sec = {
    "says_not_a_sandbox": "This is not a sandbox" in security_f,
    "says_untrusted_binary_runs_with_user_permissions": "Opening an untrusted binary delegates parsing and analysis to the selected local provider with that user's permissions" in security_f,
    "says_never_invokes_sudo": "REA never invokes `sudo`" in security_f,
    "linux_hopper_install_uses_root_or_pkexec": "pkexec" in security_f,
    "hopper_checksum_is_sha1_corruption_check": "SHA-1" in security_f and "corruption check" in security_f,
    "says_does_not_download_ghidra_or_java": "REA does not download, install, upgrade, or modify Ghidra or Java" in security_f,
    "private_reporting_channel": "Report a vulnerability" in security_f,
}
setup = {
    "shows_plan_and_needs_approval_before_writing": "Declining or pressing Ctrl-C makes no changes" in install_doc_f,
    "creates_backups_and_atomic_writes": "create backups, use atomic replacement" in install_doc_f,
    "installs_skill_under_claude_dir": "~/.claude/skills" in install_doc_f,
    "installs_shared_skill_under_agents_dir": "~/.agents/skills" in install_doc_f,
    "edits_grok_toml": "$GROK_HOME/config.toml" in install_doc_f,
}
claims = {
    "readme_example_prompt": (re.search(r"```text\n(.*?)\n```", readme, re.S) or [None, None])[1],
    "readme_says_analysis_runs_locally": "Analysis runs locally" in readme,
    "readme_upload_answer": re.sub(r"\s+", " ", (re.search(r"Does REA upload my app\?</strong></summary>\s*(.*?)\s*</details>", readme, re.S) or [None, ""])[1]),
    "readme_says_hopper_licence_prompt": "activate your license" in readme,
    "readme_names_agents": [a for a in ("Claude Code", "Codex", "Cursor", "Gemini CLI", "Grok Build") if a in readme],
}
disc = re.search(r"## Disclaimer (.*?)(?= ## |$)", readme_f)
claims["readme_disclaimer"] = disc.group(1).strip() if disc else None
claims["disclaimer_says_responsible_for_authorization_and_applicable_laws"] = bool(disc and "responsible for obtaining any required authorization and complying with applicable laws" in disc.group(1))
claims["disclaimer_warns_of_unaffiliated_tokens_using_the_name"] = bool(disc and "Tokens using the REA name are not affiliated with the project" in disc.group(1))
claims["readme_or_install_doc_mentions_eula_or_licence_terms_of_target_apps"] = bool(re.search(r"EULA|terms of (service|use)|licen[cs]e (terms|agreement) of", readme_f + " " + install_doc_f, re.I))

# ---- Submodules (third-party code vendored into the repository) ------------------------------------
subs = []
for url in re.findall(r"url = https://github.com/([^\s]+?)(?:\.git)?\s", gitmodules + "\n"):
    m = gh("/repos/" + url)
    spdx = (m.get("license") or {}).get("spdx_id") if "error" not in m else None
    row = {"repo": url, "licence_spdx": spdx, "archived": m.get("archived") if "error" not in m else None}
    if spdx in (None, "NOASSERTION"):  # GitHub could not classify it: read the licence file itself
        lic = [l.strip() for l in gh(f"/repos/{url}/contents/LICENSE", raw=True).splitlines() if l.strip()]
        row["licence_file_first_line"] = lic[0] if lic else None
    subs.append(row)
ghidra = gh("/repos/NationalSecurityAgency/ghidra")
third_party = {"submodules": subs, "ghidra_licence_spdx": (ghidra.get("license") or {}).get("spdx_id") if "error" not in ghidra else None}

# ---- The law REA's README does not mention ------------------------------------------------------------
st, page = get("https://www.law.cornell.edu/uscode/text/17/1201")
text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", "", page))))
f1 = re.search(r"Reverse Engineering\.— \(1\) (.*?)\(2\)", text)
law = {"url": "https://www.law.cornell.edu/uscode/text/17/1201", "section_1201_f_1_found": bool(f1),
       "f1_mentions_interoperability": bool(f1 and "interoperability" in f1.group(1)),
       "f1_first_words": f1.group(1)[:140] if f1 else None}

result = {"as_of": AS_OF, "repository": repo, "npm": npm_row, "install_sh": installer, "security_md": sec,
          "setup_behaviour_per_docs": setup, "readme_claims": claims,
          "package_json_at_tag": {"version": pkg.get("version"), "bin": sorted((pkg.get("bin") or {}).keys()),
                                   "install_hooks": [k for k in (pkg.get("scripts") or {}) if k in ("preinstall", "install", "postinstall")],
                                   "prepare_script_present": "prepare" in (pkg.get("scripts") or {}),
                                   "dependency_count": len(pkg.get("dependencies", {}))},
          "third_party": third_party, "law": law}
json.dump(result, sys.stdout, indent=2, sort_keys=True)
sys.stdout.write("\n")
