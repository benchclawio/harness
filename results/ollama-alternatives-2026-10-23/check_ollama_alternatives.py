#!/usr/bin/env python3
"""Read public records about Ollama and nine alternatives, print one JSON document.

Standard library only, no account, nothing billed, nothing installed or run, no model called. Reads:
  - GitHub's API for eight repositories (Ollama and seven alternatives): licence (SPDX and the licence file at the repository root), archived flag,
    canonical name, last commit, latest stable release, stable releases in the 90 days before the cut-off, published security advisories,
    README sentences about ownership or maintenance
  - the repositories in the lmstudio-ai GitHub organisation (LM Studio's app is not one of them), with their licences
  - PyPI for vLLM and GPT4All: latest stable version, upload date, versions in 90 days
  - Ollama's repository root: whether it vendors llama.cpp and has its own runner directory
  - vendor pages: Ollama pricing and its context-length documentation, LM Studio's app terms, Msty's pricing, and Atomic Chat's own
    "10 Best Ollama Alternatives in 2026" article
  - google-ai-overview-ollama-alternatives-2026-10-23.md, saved next to this script, to check its claims

Dates use a fixed cut-off (--as-of 2026-10-23T14:30:00Z). Pages and READMEs are read live. Optional GITHUB_TOKEN lifts GitHub's 60-requests-an-hour
limit; the script makes about 150 GitHub requests (vLLM alone needs about 10 pages of advisories), so set it.

Usage: python3 check_ollama_alternatives.py [--as-of 2026-10-23T14:30:00Z] > out.json
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
AS_OF = "2026-10-23T14:30:00Z"
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


def gh_pages(path, limit=8):
    out = []
    for page in range(1, limit + 1):
        batch = gh(f"{path}{'&' if '?' in path else '?'}per_page=100&page={page}")
        if not isinstance(batch, list):
            return out, False
        out += batch
        if len(batch) < 100:
            return out, True
    return out, False


LIMITS = {"llama.cpp": 25, "vLLM": 40}


def gh_cursor(path, limit=40):
    """The security-advisories endpoint paginates by cursor (Link header), and ignores ?page=N."""
    out, url = [], "https://api.github.com" + path + ("&" if "?" in path else "?") + "per_page=100"
    h = {"User-Agent": UA, "Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        h["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    for _ in range(limit):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=40) as r:
                batch = json.loads(r.read().decode("utf-8", "replace"))
                link = r.headers.get("Link") or ""
        except Exception:
            return out, False
        out += batch
        nxt = re.search(r'<([^>]+)>;\s*rel="next"', link)
        if not nxt:
            return out, True
        url = nxt.group(1)
    return out, False


# ---- 1. Repositories ---------------------------------------------------------------------------------------
REPOS = [("Ollama", "ollama/ollama", None, r"^v\d+\.\d+\.\d+$"),
         ("Jan", "janhq/jan", None, r"^v\d+\.\d+\.\d+$"),
         ("llama.cpp", "ggml-org/llama.cpp", None, r"^b\d+$"),
         ("vLLM", "vllm-project/vllm", "vllm", r"^v\d+\.\d+\.\d+$"),
         ("LocalAI", "mudler/LocalAI", None, r"^v\d+\.\d+\.\d+$"),
         ("GPT4All", "nomic-ai/gpt4all", "gpt4all", r"^v\d+\.\d+\.\d+$"),
         ("text-generation-webui", "oobabooga/text-generation-webui", None, r"^v\d+(?:\.\d+)*$"),
         ("Atomic Chat", "AtomicBot-ai/Atomic-Chat", None, r"^v\d+\.\d+\.\d+$")]
LICENCE_PATHS = ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING")
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


def licence_info(full_name):
    for p in LICENCE_PATHS:
        lic = gh(f"/repos/{full_name}/contents/{p}", raw=True)
        if lic:
            lines = [l.strip() for l in lic.splitlines() if l.strip()]
            return {"found_at_repository_root": p, "first_line": lines[0][:100] if lines else None,
                    "copyright_lines": [l[:100] for l in lines if l.lower().startswith("copyright")][:3],
                    "names_agpl": "GNU AFFERO GENERAL PUBLIC LICENSE" in lic.upper(), "names_gpl_not_affero": "GNU GENERAL PUBLIC LICENSE" in lic.upper(),
                    "names_apache": "Apache License" in lic, "names_mit": "MIT License" in lic or "MIT license" in lic}
    return {"found_at_repository_root": None}


def repo_row(name, repo, pypi_pkg, tag_re):
    meta = gh("/repos/" + repo)
    if "error" in meta:
        return {"name": name, "repo": repo, "error": meta["error"]}
    out = {"name": name, "repo": repo, "canonical_repo": meta["full_name"], "licence_spdx": (meta.get("license") or {}).get("spdx_id"), "archived": meta["archived"],
           "is_github_fork": meta.get("fork"), "github_description": (meta.get("description") or "")[:160], "licence_file": licence_info(meta["full_name"])}
    commit = gh(f"/repos/{repo}/commits?per_page=1&until={AS_OF}")
    out["last_commit_before_cutoff"] = commit[0]["commit"]["committer"]["date"][:10] if isinstance(commit, list) and commit else None
    all_rels, exhausted = gh_pages(f"/repos/{repo}/releases", LIMITS.get(name, 8))
    rels = [r for r in all_rels if isinstance(r, dict) and not r.get("draft") and r.get("published_at") and parse(r["published_at"]) <= CUT]
    stable = sorted((r for r in rels if not r.get("prerelease") and re.search(tag_re, r["tag_name"])
                     and not re.search(r"nightly|alpha|beta|rc|dev|preview|canary", r["tag_name"], re.I)), key=lambda r: r["published_at"])
    oldest = min((r["published_at"] for r in rels), default=None)
    matching = [r for r in rels if re.search(tag_re, r["tag_name"])]
    out["tagged_releases_matching_pattern_in_90_days_including_prereleases"] = sum(1 for r in matching if (CUT - parse(r["published_at"])).days < 90)
    out["matching_releases_marked_prerelease_by_github"] = sum(1 for r in matching if r.get("prerelease"))
    out["newest_matching_release"] = ({"tag": max(matching, key=lambda r: r["published_at"])["tag_name"], "date": max(r["published_at"] for r in matching)[:10]} if matching else None)
    latest = gh(f"/repos/{repo}/releases/latest")
    out["github_latest_release_marker"] = ({"tag": latest["tag_name"], "date": latest["published_at"][:10]} if isinstance(latest, dict) and "tag_name" in latest else None)
    out["latest_stable_release"] = ({"tag": stable[-1]["tag_name"], "date": stable[-1]["published_at"][:10], "days_before_cutoff": (CUT - parse(stable[-1]["published_at"])).days}
                                    if stable else None)
    out["stable_releases_in_90_days"] = sum(1 for r in stable if (CUT - parse(r["published_at"])).days < 90)
    out["release_window_fully_listed"] = bool(exhausted or (oldest and (CUT - parse(oldest)).days >= 90))
    advs, adv_exhausted = gh_cursor(f"/repos/{repo}/security-advisories", LIMITS.get(name, 8))
    advs = list({a["ghsa_id"]: a for a in advs if isinstance(a, dict) and a.get("ghsa_id") and a.get("published_at") and parse(a["published_at"]) <= CUT}.values())
    out["advisory_listing_complete"] = adv_exhausted
    out["published_advisories"] = {"total": len(advs), "last_12_months": sum(1 for a in advs if (CUT - parse(a["published_at"])).days < 365),
                                   "by_severity": {s: sum(1 for a in advs if (a.get("severity") or "unknown") == s) for s in sorted({a.get("severity") or "unknown" for a in advs})},
                                   "latest": max((a["published_at"][:10] for a in advs), default=None)}
    readme = re.sub(r"\s+", " ", gh(f"/repos/{repo}/readme", raw=True))
    out["readme_status_sentences"] = [s.strip()[:200] for s in STATUS.findall(readme)][:3]
    out["readme_mentions_jan_or_menlo"] = bool(re.search(r"\bJan\b|Menlo", readme))
    out["readme_first_sentence_naming_jan_or_menlo"] = next((s.strip()[:200] for s in re.split(r"(?<=[.!?]) ", readme) if re.search(r"\bJan\b|Menlo", s)), None)
    out["registry"] = pypi_row(pypi_pkg) if pypi_pkg else None
    return out


rows = [repo_row(*r) for r in REPOS]
by = {r["name"]: r for r in rows}

# ---- 2. LM Studio's GitHub organisation and Ollama's repository layout ----------------------------------------------------
lm_org = gh("/orgs/lmstudio-ai/repos?per_page=100&sort=pushed")
lm_repos = {r["name"]: {"licence_spdx": (r.get("license") or {}).get("spdx_id"), "archived": r["archived"], "last_push": r["pushed_at"][:10]}
            for r in (lm_org if isinstance(lm_org, list) else []) if r["name"] in ("lms", "lmstudio-js", "lmstudio-python", "lmstudio-bug-tracker", "mlx-engine")}
root = gh("/repos/ollama/ollama/contents")
llama_dir = gh("/repos/ollama/ollama/contents/llama")
llama_readme = re.sub(r"\s+", " ", gh("/repos/ollama/ollama/contents/llama/README.md", raw=True))
ollama_layout = {"root_directories_of_interest": sorted(i["name"] for i in root if i["type"] == "dir" and i["name"] in ("llama", "llm", "ml", "mlx", "model")) if isinstance(root, list) else None,
                 "llama_directory_entries": sorted(i["name"] for i in llama_dir) if isinstance(llama_dir, list) else None,
                 "llama_readme_says_LLAMA_CPP_VERSION_pins_llama_cpp_source": "`LLAMA_CPP_VERSION` pins Ollama's llama.cpp source" in llama_readme,
                 "llama_readme_mentions_llama_server": "llama-server" in llama_readme}

# ---- 3. Vendor pages -----------------------------------------------------------------------------------------------------
pricing = text_of(get("https://ollama.com/pricing")[1])
ctx = text_of(get("https://docs.ollama.com/context-length")[1])
ollama = {"pricing_page": {"free": find(r"(Free \$0)", pricing, 1), "pro": find(r"(Pro \$20 / mo\.)", pricing) or find(r"(\$20 / mo\.)", pricing),
                           "team": find(r"(\$500 / mo\.)", pricing), "free_plan_includes_run_models_locally": "Run models locally" in pricing},
          "context_length_docs": {"says_4k_under_24_gib": bool(re.search(r"< ?24 GiB VRAM:? 4k context", ctx)), "says_32k_24_to_48_gib": bool(re.search(r"24-48 GiB VRAM:? 32k context", ctx)),
                                  "says_256k_over_48_gib": bool(re.search(r">= ?48 GiB VRAM:? 256k context", ctx)), "mentions_2048": "2048" in ctx,
                                  "says_agent_tasks_need_at_least_64000": "at least 64000 tokens" in ctx}}

terms = text_of(get("https://lmstudio.ai/app-terms")[1])
lmstudio = {"app_terms": {"company": find(r"(Element Labs, Inc\.)", terms, 1), "version_line": find(r"(Version: [A-Z][a-z]+ \d{1,2}, \d{4})", terms, 1),
                          "licence_grant": find(r"(non-exclusive, non-transferable license to use the Software solely for Your personal and / or internal business purposes)", terms, 1),
                          "says_source_code_is_trade_secret": "source code constitute valuable trade secrets" in terms, "forbids_reverse_engineering": "reverse engineer, decompile, disassemble" in terms},
            "github_org_repositories": lm_repos}

msty_page = text_of(get("https://msty.ai/pricing")[1])
msty = {"free": find(r"(Free \$0 Forever)", msty_page, 1), "aurum": find(r"(Aurum \$149 USD per user / year)", msty_page, 1), "aurum_lifetime": find(r"(Aurum Lifetime \$349 USD per user)", msty_page, 1),
        "company": find(r"(Msty is a product of CloudStack, LLC)", msty_page, 1), "lists_local_engines": find(r"(Local Inference Engines - Ollama, Llama\.cpp, MLX)", msty_page, 1)}

atomic = text_of(get("https://atomic.chat/blog/llm-updates/ollama-alternatives")[1])
atomic_article = {"title": find(r"(10 Best Ollama Alternatives in 2026)", atomic, 1), "author": find(r"(Andrew Dyuzhov)", atomic, 1),
                  "times_it_says_Atomic_Chat": atomic.count("Atomic Chat"),
                  "ranks_itself_best_overall": "Best overall (GUI + mobile + free): Atomic Chat" in atomic,
                  "lists_itself_first_in_deep_dive": "1. Atomic Chat" in atomic,
                  "says_atomic_chat_apache_2_0": "Apache-2.0, zero cost" in atomic,
                  "says_ollama_defaults_num_ctx_to_2048": "defaults num_ctx to 2048" in atomic,
                  "says_ollama_moved_off_llama_cpp_to_own_go_engine": "Ollama's move off llama.cpp to its own Go engine" in atomic}

xda = text_of(get("https://www.xda-developers.com/ollama-alternatives-worth-trying/")[1])
xda_article = {"title": find(r"(Ollama is the easiest way to start local LLMs, but these 6 alternatives are also worth trying)", xda, 1), "published": find(r"(Published [A-Z][a-z]{2} \d{1,2}, \d{4})", xda, 1),
               "says_llama_cpp_is_engine_ollama_runs_on": "inference engine that Ollama itself runs on" in xda,
               "names_found": [n for n in ("LM Studio", "llama.cpp", "KoboldCpp", "Jan", "vLLM", "LocalAI", "GPT4All", "Msty") if n.lower() in xda.lower()]}

# ---- 4. Google's AI Overview ---------------------------------------------------------------------------------------------
aio = open(os.path.join(HERE, "google-ai-overview-ollama-alternatives-2026-10-23.md"), encoding="utf-8").read()
overview_part = aio.split("## Sources cited by the overview")[0]
refs_part = aio.split("## Sources cited by the overview")[1].split("## Organic results")[0]
jan = by["Jan"]
claims = {
    "overview_names": [n for n in ("LM Studio", "Jan", "Atomic Chat", "GPT4All", "Msty AI", "llama.cpp", "LocalAI", "Text-generation-webui", "vLLM") if n in overview_part],
    "overview_cites_atomic_chat_vendor_article": "atomic.chat/blog/llm-updates/ollama-alternatives" in refs_part,
    "overview_says_jan_apache_2_0": "Apache-2.0" in overview_part and "Jan" in overview_part,
    "jan_github_licence_spdx": jan.get("licence_spdx"), "jan_licence_file_first_line": jan.get("licence_file", {}).get("first_line"),
    "jan_licence_file_names_apache": jan.get("licence_file", {}).get("names_apache"),
    "atomic_chat_licence_file_copyright_lines": by["Atomic Chat"].get("licence_file", {}).get("copyright_lines"),
    "atomic_chat_is_github_fork": by["Atomic Chat"].get("is_github_fork"), "atomic_chat_readme_mentions_jan_or_menlo": by["Atomic Chat"].get("readme_mentions_jan_or_menlo"),
    "atomic_article_mentions_jan_derivation": bool(re.search(r"fork of Jan|based on Jan|built on Jan|derived from Jan|Menlo", atomic)),
    "overview_says_lm_studio_has_openai_compatible_api": "LM Studio" in overview_part and "OpenAI-compatible local API server" in overview_part,
    "overview_says_lm_studio_is_open_source": bool(re.search(r"LM Studio[^.]*open.source", overview_part, re.I)),
    "overview_mentions_pricing_or_licence_of_lm_studio": bool(re.search(r"LM Studio[^.]*(?:free|paid|licen)", overview_part, re.I)),
    "overview_says_llama_cpp_runs_underneath_many_local_tools": "running underneath many local tools" in overview_part,
    "overview_mentions_a_dollar_price": bool(re.search(r"\$\d", overview_part)),
    "overview_mentions_ollama_pro_or_team_plan": bool(re.search(r"Ollama (?:Pro|Team)|Ollama Cloud|Ollama's (?:paid|cloud)", overview_part)),
    "ollama_has_pro_and_team_plans_for_cloud_models": bool(ollama["pricing_page"]["pro"] and ollama["pricing_page"]["team"]),
}

json.dump({"as_of": AS_OF, "repositories": rows, "ollama_repository_layout": ollama_layout, "ollama": ollama, "lm_studio": lmstudio, "msty": msty,
           "atomic_chat_article": atomic_article, "xda_article": xda_article, "claims_checked": claims}, sys.stdout, indent=2, sort_keys=True)
sys.stdout.write("\n")
