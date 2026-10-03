"""Check what is publicly verifiable about Guardrails AI after the Harvey acquisition.

Standard library only; no API keys. Reads Harvey's announcement, the GitHub REST API,
PyPI, pypistats.org and two retired Guardrails endpoints. Prints one JSON document.
"""
import json
import re
import socket
import urllib.error
import urllib.request
from collections import Counter, defaultdict

UA = {"User-Agent": "Mozilla/5.0 (benchclaw-guardrails-check)"}
REPO = "guardrails-ai/guardrails"
DEAL = "2026-09-08"  # date shown on guardrailsai.com's copy of the announcement


def get(url, raw=False):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode()
    return body if raw else json.loads(body)


def gh(path):
    return get(f"https://api.github.com/repos/{REPO}{path}")


out = {"checked_on": "2026-10-03", "deal_date_used": DEAL}

# 1. The announcement
post = get("https://www.harvey.ai/blog/guardrails-ai-joins-harvey", raw=True)
start = post.index("Harvey today announced")
end = post.index("build safe, reliable AI that professionals can trust") + 60
post = post[start:end]  # article body only; the page banner mentions an unrelated funding round
out["announcement"] = {
    "says_acquisition": "announced its acquisition of San Francisco-based" in post,
    "says_250k_monthly": "downloaded more than 250,000 times a month" in post,
    "mentions_open_source_future": bool(re.search(r"open[- ]source (project|framework) (will|remain|continue)", post, re.I)),
    "mentions_price_or_terms": bool(re.search(r"\$\s?\d|undisclosed|terms of the", post, re.I)),
}

# 2. Repository state
meta = gh("")
out["repo"] = {
    "license": meta["license"]["spdx_id"],
    "archived": meta["archived"],
    "owner": meta["owner"]["login"],
    "stars": meta["stargazers_count"],
    "pushed_at": meta["pushed_at"],
}
commits, page = [], 1
while True:
    chunk = gh(f"/commits?since=2026-01-01T00:00:00Z&per_page=100&page={page}")
    commits += chunk
    if len(chunk) < 100:
        break
    page += 1
dates = [c["commit"]["author"]["date"] for c in commits]
out["commits_to_default_branch"] = {
    "by_month_2026": dict(sorted(Counter(d[:7] for d in dates).items())),
    "latest": max(dates),
    "on_or_after_deal_date": sum(d[:10] >= DEAL for d in dates),
}
rel = gh("/releases?per_page=5")
out["latest_releases"] = [[r["tag_name"], r["published_at"]] for r in rel]

# 3. README
readme = get(f"https://raw.githubusercontent.com/{REPO}/main/README.md", raw=True)
out["readme"] = {
    "mentions_harvey_or_acquisition": len(re.findall(r"harvey|acqui", readme, re.I)),
    "news_entries": re.findall(r"^- \*\*\[([^\]]+)\]\*\*", readme, re.M),
}

# 4. Open 1.0 design issue
iss = gh("/issues/1591")
cm = gh("/issues/1591/comments")
out["issue_1591_1_0_roadmap"] = {
    "title": iss["title"],
    "last_human_comment": max(c["created_at"] for c in cm if c["user"]["type"] != "Bot"),
    "stale_bot_comment": [c["created_at"] for c in cm if c["user"]["type"] == "Bot"],
}

# 5. PyPI and downloads
pkg = get("https://pypi.org/pypi/guardrails-ai/json")
out["pypi"] = {"version": pkg["info"]["version"], "license": pkg["info"]["license"]}
dl = get("https://pypistats.org/api/packages/guardrails-ai/overall")["data"]
by = defaultdict(lambda: defaultdict(int))
for r in dl:
    by[r["date"][:7]][r["category"]] += r["downloads"]
out["monthly_downloads_pypistats"] = {m: dict(v) for m, v in sorted(by.items())}
for cat in ("with_mirrors", "without_mirrors"):
    rows = sorted((r for r in dl if r["category"] == cat), key=lambda r: r["date"])
    out[f"last_30_days_{cat}"] = {"through": rows[-1]["date"], "downloads": sum(r["downloads"] for r in rows[-30:])}
out["pypistats_recent_endpoint"] = get("https://pypistats.org/api/packages/guardrails-ai/recent")["data"]
out["pepy_last_30_days"] = None
try:
    pp = get("https://pepy.tech/api/v2/projects/guardrails-ai")["downloads"]
    days = sorted(pp)[-31:-1]
    out["pepy_last_30_days"] = {"through": days[-1], "downloads": sum(sum(pp[d].values()) for d in days)}
except Exception as exc:  # pepy is optional corroboration
    out["pepy_last_30_days"] = f"unavailable: {exc}"

# 6. Retired endpoints
probe = {}
try:
    socket.getaddrinfo("hub.api.guardrailsai.com", 443)
    probe["hub.api.guardrailsai.com"] = "resolves"
except socket.gaierror as exc:
    probe["hub.api.guardrailsai.com"] = f"DNS failure: {exc.strerror}"
try:
    get("https://pypi.guardrailsai.com/simple/", raw=True)
    probe["pypi.guardrailsai.com/simple/"] = "HTTP 200"
except urllib.error.HTTPError as exc:
    probe["pypi.guardrailsai.com/simple/"] = f"HTTP {exc.code} without credentials"
out["retired_endpoints"] = probe

print(json.dumps(out, indent=2))
