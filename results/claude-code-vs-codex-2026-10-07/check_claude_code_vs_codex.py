#!/usr/bin/env python3
"""Read published facts about Claude Code and OpenAI Codex, print one JSON document.

Standard library only, no API key, no account, nothing is billed and neither tool is run.
Reads the npm registry entries for the two CLI packages, the two GitHub repositories, and the two
vendors' public pricing pages (parsed into numbers). This is metadata and published pricing, not a
measurement of how either tool performs.
"""
import datetime
import json
import os
import re
import sys
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (benchclaw claude-code-vs-codex check)", "Accept": "application/json, text/html"}
TODAY = datetime.date.today()


def get(url, text=False):
    headers = dict(UA)
    token = os.environ.get("GITHUB_TOKEN")  # optional: only lifts GitHub's 60-requests-an-hour limit
    if token and url.startswith("https://api.github.com/"):
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=40) as r:
        body = r.read().decode("utf-8", "replace")
    return body if text else json.loads(body)


def stable(v):
    return bool(re.fullmatch(r"\d+(\.\d+)*", v))


def npm(pkg, repo):
    d = get(f"https://registry.npmjs.org/{pkg.replace('/', '%2F')}")
    latest = d["dist-tags"]["latest"]
    v = d["versions"][latest]
    times = {k: t[:10] for k, t in d["time"].items() if stable(k)}
    row = {"package": pkg, "latest": latest, "latest_published": d["time"][latest][:10],
           "days_since_latest": (TODAY - datetime.date.fromisoformat(d["time"][latest][:10])).days,
           "releases_last_90_days": sum(1 for t in times.values() if (TODAY - datetime.date.fromisoformat(t)).days <= 90),
           "first_release": min(times.values()), "npm_license_field": v.get("license"),
           "runtime_dependencies": len(v.get("dependencies") or {})}
    g = get(f"https://api.github.com/repos/{repo}")
    row.update({"repo": repo, "github_license": (g.get("license") or {}).get("spdx_id"), "github_archived": g["archived"],
                "github_pushed_at": g["pushed_at"][:10], "github_language": g.get("language")})
    try:
        lic = get(f"https://raw.githubusercontent.com/{repo}/HEAD/LICENSE.md", text=True)
    except Exception:
        try:
            lic = get(f"https://raw.githubusercontent.com/{repo}/HEAD/LICENSE", text=True)
        except Exception:
            lic = ""
    row["license_file_first_line"] = lic.strip().splitlines()[0][:140] if lic.strip() else None
    return row


def flat(html):
    t = re.sub(r"<(script|style).*?</\1>", " ", html, flags=re.S)
    t = re.sub(r"<[^>]+>", "|", t)
    return re.sub(r"\s*\|\s*(\|\s*)*", "|", re.sub(r"\s+", " ", t))


claude_txt = flat(get("https://claude.com/pricing", text=True))
codex_txt = flat(get("https://developers.openai.com/codex/pricing", text=True))


def first(p, s, cast=int):
    m = re.search(p, s)
    return cast(m.group(1).replace(",", "")) if m else None


pro_seg = claude_txt[claude_txt.find("|Pro|"): claude_txt.find("|Max|")]
usage_rows = {}
for m in re.finditer(r"(GPT-[0-9.]+ [A-Za-z]+)\|(\d[\d,]*-\d[\d,]*)\|(\d[\d,]*-\d[\d,]*)\|", codex_txt):
    usage_rows.setdefault(m.group(1), {"plus": m.group(2), "standard_business": m.group(3)})

pricing = {
    "claude": {
        "pro_usd_monthly_billing": first(r"\|\$(\d+)\|if billed monthly", claude_txt),
        "pro_usd_per_month_annual_billing": first(r"\|\$(\d+)\|Per month with annual subscription discount", claude_txt),
        "pro_includes_claude_code": "Claude Code" in pro_seg,
        "max_from_usd_per_month": first(r"From \$(\d+)\|Per month", claude_txt) or first(r"From\|\$(\d+)\|Per month", claude_txt),
        "max_usage_wording": "Choose 5x or 20x more usage than Pro*" if "Choose 5x or 20x more usage than Pro" in claude_txt else None,
        "publishes_absolute_usage_numbers": bool(re.search(r"\d[\d,]*\s*(messages|prompts|requests)\s*(per|every|/)", claude_txt)),
    },
    "codex": {
        "free_usd": first(r"\|Free\|[^|]*\|\$(\d+)\|/month", codex_txt),
        "go_usd": first(r"\|Go\|[^|]*\|\$(\d+)\|/month", codex_txt),
        "plus_usd": first(r"\|Plus\|[^|]*\|\$(\d+)\|/month", codex_txt),
        "pro_from_usd": first(r"From\|\$(\d+)\|/month", codex_txt),
        "pro_plans_usd": re.findall(r"Plans at \$(\d+), \$(\d+), or \$(\d+) USD per month", codex_txt),
        "included_in_chatgpt_plans": "ChatGPT Work and Codex are included in your ChatGPT" in codex_txt,
        "plus_includes_cli": "Codex on the web, in the CLI, in the IDE extension" in codex_txt,
        "api_key_option_pay_per_api_pricing": "Pay for Codex usage based on|API pricing" in codex_txt,
        "local_messages_per_5_hours": usage_rows,
        "gpt_5_5_retirement": (re.search(r"GPT-5\.5 retires from ChatGPT[^.]*? on\|?\s*([A-Z][a-z]+ \d+, \d{4})", codex_txt) or [None, None])[1],
        "models_named_on_plus": [m for m in ("GPT-6.1 Sol", "GPT-6 Luna") if m in codex_txt],
    },
}

json.dump({"read_on": TODAY.isoformat(),
           "claude_code": npm("@anthropic-ai/claude-code", "anthropics/claude-code"),
           "codex": npm("@openai/codex", "openai/codex"),
           "pricing_pages_read": ["https://claude.com/pricing", "https://developers.openai.com/codex/pricing"],
           "pricing": pricing}, sys.stdout, indent=2)
print()
