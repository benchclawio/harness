#!/usr/bin/env python3
"""Read licence, last stable release, last commit and Anthropic mentions for Claude Code and eight alternatives.

Standard library only; no key needed. Set GITHUB_TOKEN (optional) to lift GitHub's 60-requests-an-hour limit.
Per repository it makes GitHub requests for the repo, its releases (up to 5 pages), its licence, its README and its
last commit before the cut-off, plus one read of a documentation page that should name the Anthropic provider.

Release and commit dates use a fixed cut-off (--as-of) so two runs minutes apart agree even for repositories that
publish many times a day. The licence, archived flag, README and documentation text are the state when you run it.
A release counts as stable when GitHub does not flag it a pre-release, its tag has none of: nightly, alpha, beta, rc,
preview, canary, dev, and its tag matches the main product series (Cline also tags cli-, desktop- and sdk/ releases;
Codex publishes its CLI as rust-vX.Y.Z). If five pages of releases hold no stable one, GitHub's own latest-release
endpoint is used. Nothing is installed or executed, no model is called, and page mentions are not tests.

Usage: python3 check_coding_agents.py [--as-of 2026-10-08T18:00:00Z]
"""
import argparse, base64, concurrent.futures, datetime, json, os, re, urllib.request, urllib.error

TOOLS = [
    # name, repo, page that should say which model providers it supports (None = README only),
    # and a regex for the tag series of the main product when one repository publishes several
    ("Claude Code", "anthropics/claude-code", None, r"^v\d"),
    ("OpenCode", "anomalyco/opencode", "https://opencode.ai/docs/providers/", r"^v\d"),
    ("Aider", "Aider-AI/aider", "https://aider.chat/docs/llms/anthropic.html", r"^v\d"),
    ("Cline", "cline/cline", "https://docs.cline.bot/provider-config/anthropic", r"^v\d"),
    ("Codex CLI", "openai/codex", "https://developers.openai.com/codex/config-advanced", r"^rust-v\d+\.\d+\.\d+$"),
    ("Gemini CLI", "google-gemini/gemini-cli", None, r"^v\d"),
    ("Goose", "block/goose", "https://goose-docs.ai/docs/getting-started/providers", r"^v\d"),
    ("GitHub Copilot CLI", "github/copilot-cli", "https://docs.github.com/en/copilot/concepts/agents/about-copilot-cli", r"^v\d"),
    ("Crush", "charmbracelet/crush", None, r"^v\d"),
]
UA = {"User-Agent": "Mozilla/5.0 (benchclaw-check/1.0)"}
PRE = re.compile(r"nightly|alpha|beta|rc|preview|canary|dev", re.I)


def get(url, headers=None, timeout=40):
    h = dict(UA); h.update(headers or {})
    for attempt in (1, 2):  # one retry on a server error or timeout, no more
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


def api(path, raw=False):
    h = {"Accept": "application/vnd.github.raw+json" if raw else "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        h["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    st, body = get("https://api.github.com" + path, h)
    if st != 200:
        return {"error": st}
    return body if raw else json.loads(body)


def parse(ts):
    return datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)


def one(item, as_of):
    name, repo, docs, tag_re = item
    tag_re = re.compile(tag_re)
    out = {"name": name, "repo": repo}
    d = api("/repos/" + repo)
    if "error" in d:
        out["error"] = d["error"]; return out
    out["canonical_repo"] = d["full_name"]
    out["archived"] = d["archived"]
    out["licence_spdx"] = (d.get("license") or {}).get("spdx_id")
    lic = api("/repos/%s/license" % repo)
    out["licence_file_first_line"] = None
    if isinstance(lic, dict) and lic.get("content"):
        txt = base64.b64decode(lic["content"]).decode("utf-8", "replace")
        out["licence_file_first_line"] = next((l.strip() for l in txt.splitlines() if l.strip()), "")[:120]
    elif name == "Claude Code":
        st, txt = get("https://raw.githubusercontent.com/anthropics/claude-code/main/LICENSE.md")
        out["licence_file_first_line"] = next((l.strip() for l in txt.splitlines() if l.strip()), "")[:120] if st == 200 else None
    stable = None
    for page in range(1, 6):
        rel = api("/repos/%s/releases?per_page=100&page=%d" % (repo, page))
        if not isinstance(rel, list) or not rel:
            break
        for r in rel:
            if r.get("draft") or r.get("prerelease") or PRE.search(r.get("tag_name", "")) or not r.get("published_at") or not tag_re.search(r.get("tag_name", "")):
                continue
            t = parse(r["published_at"])
            if t <= as_of and (stable is None or t > stable[0]):
                stable = (t, r["tag_name"])
        if stable:
            break
    if stable is None:  # a flood of pre-releases can push the last stable release past the pages read
        lt = api("/repos/%s/releases/latest" % repo)
        if isinstance(lt, dict) and lt.get("published_at") and tag_re.search(lt.get("tag_name", "")):
            t = parse(lt["published_at"])
            if t <= as_of:
                stable = (t, lt["tag_name"])
    out["latest_stable_release_before_cutoff"] = {"tag": stable[1], "date": stable[0].strftime("%Y-%m-%d"),
                                                  "days_before_cutoff": (as_of - stable[0]).days} if stable else None
    cm = api("/repos/%s/commits?per_page=1&until=%s" % (repo, as_of.strftime("%Y-%m-%dT%H:%M:%SZ")))
    if isinstance(cm, list) and cm:
        t = parse(cm[0]["commit"]["committer"]["date"])
        out["last_commit_before_cutoff"] = {"date": t.strftime("%Y-%m-%d"), "days_before_cutoff": (as_of - t).days}
    else:
        out["last_commit_before_cutoff"] = None
    rd = api("/repos/%s/readme" % repo, raw=True)
    rtext = rd if isinstance(rd, str) else ""
    pat = re.compile(r"(free tier|requests ?/ ?(day|min)|active .*subscription|bring your own|your own (api )?key|byok)", re.I)
    out["readme_pricing_or_key_lines"] = [re.sub(r"\s+", " ", l).strip(" -*>|#")[:200] for l in rtext.splitlines() if pat.search(l) and len(l) > 8][:2]
    out["readme_anthropic_mentions"] = len(re.findall(r"anthropic", rtext, re.I))
    if docs:
        st, page = get(docs)
        out["provider_page"] = {"url": docs, "http": st, "anthropic_mentions": len(re.findall(r"anthropic", page, re.I))}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default="2026-10-08T18:00:00Z")
    a = ap.parse_args()
    as_of = parse(a.as_of)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        rows = list(ex.map(lambda it: one(it, as_of), TOOLS))
    print(json.dumps({"as_of": a.as_of, "tools": rows}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
