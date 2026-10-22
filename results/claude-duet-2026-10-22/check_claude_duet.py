#!/usr/bin/env python3
"""Read the published pages about Claude Duet and ChatGPT dots, and record which statements they make. Prints one JSON document.

Standard library only, no account, no waitlist signup, nothing billed, no model called, and Claude Duet itself is never run. Reads:
  - Anthropic's announcement (claude.com/resources/articles/claude-duet), dated 2026-10-21
  - Anthropic's help-centre article "Get started with Claude Duet" (limitations, pricing and limits, privacy)
  - Anthropic's pricing page (Pro and Max prices only, to price the plans Duet is included in)
  - OpenAI's "Meet dots" documentation (what a dot is, who has access), for the comparison table
  - three press reports (MacRumors, Engadget, Unite.AI), only to record where their wording differs from Anthropic's own pages

Each entry in "statements" is a sentence or phrase copied from a page; the value says whether that exact text (apostrophes normalised) is on the page
today. Pages are read live and Anthropic's help article is marked "Updated today", so a later run can differ. --as-of is a label, not a filter.

Usage: python3 check_claude_duet.py [--as-of 2026-10-22] > out.json
"""
import html
import json
import re
import sys
import urllib.error
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36", "Accept-Language": "en-US,en;q=0.9"}
AS_OF = sys.argv[sys.argv.index("--as-of") + 1] if "--as-of" in sys.argv else "2026-10-22"


def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return 0, ""


def must(url):
    st, body = get(url)
    if st != 200 or not body:
        sys.exit("abort: %s returned %s" % (url, st))
    return body


def flat(raw):
    t = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", "", raw)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    t = t.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace(" ", " ")
    t = re.sub(r"\s+", " ", t).strip()
    return re.sub(r" ([,.;:!?])", r"\1", t)   # tags between a link and its punctuation leave a stray space


def has(text, phrase):
    return phrase.replace("’", "'") in text


URLS = {"announcement": "https://claude.com/resources/articles/claude-duet",
        "help": "https://support.claude.com/en/articles/17631495-get-started-with-claude-duet",
        "pricing": "https://claude.com/pricing",
        "openai_dots": "https://learn.chatgpt.com/docs/dots",
        "macrumors": "https://www.macrumors.com/2026/10/21/anthropic-claude-duet/",
        "engadget": "https://www.engadget.com/2293646/claude-duet-is-anthropics-answer-to-meta-muse-and-openai-dots/",
        "unite": "https://www.unite.ai/anthropic-opens-claude-duet-research-preview-to-us-pro-and-max-users/"}
raw = {k: must(u) for k, u in URLS.items()}
T = {k: flat(v) for k, v in raw.items()}

ANNOUNCEMENT = [
    "A research preview is available by waitlist today, starting with US Pro and Max subscribers.",
    "Date October 21, 2026",
    "a new app where Claude works as a proactive agent",
    "keeps working even when you step away, and checks with you before it acts on your behalf",
    "built Claude Duet for professionals and small business owners",
    "available as a standalone app on iOS and Android, and on claude.ai",
    "Claude Duet is included in Pro and Max plans and uses the same usage limits as the rest of Claude",
    "We designed it around Claude Opus 5.5",
    "Each morning, it sends you a short brief on the most important items across your connected apps",
    "Claude Duet checks your connected accounts every few hours, because checking nonstop would use up your plan's limits much faster",
    "it shows you exactly what it's about to do and waits for your approval",
    "A few things are off-limits even with your approval, like trading securities or moving money between accounts",
    "over 6,000 connectors and plugins in the Claude Marketplace",
    "it never directly sees your passwords or sign-in tokens",
    "Actions are approved by our auto mode classifier",
    "a new dedicated classifier and safety system prompt that checks each message",
    "reject requests to share the strictest tier of information, including credit card numbers and government identification",
    "Other sensitive information, such as health or personal finances, are let through only when you've explicitly instructed Claude Duet to send it",
    "Red teams and an external firm penetration tested Claude Duet, and it's covered by our public bug bounty program",
    "will share more details about how Claude Duet is designed for safety in the coming days",
    "it can't yet show you its browser",
    "Claude Duet lives in its own app, separate from the main Claude app",
    "Claude Duet has a virtual machine with its own browser",
    "Link, Stripe's digital wallet",
    "Shop Pay from Shopify",
    "Coming soon, with your permission, it will be able to sign in to sites with logins you've saved in 1Password",
    "it still might misread a thread or miscalibrate what's urgent",
    "personal errands, such as booking tickets, aren't quite as strong",
]
HELP = [
    "Claude Duet is available as a research preview to users on the Pro and Max plans in the US, through a waitlist",
    "It isn't available on Team or Enterprise plans yet",
    "Access opens in waves",
    "An invitation from the waitlist",
    "You can't choose a model. Claude Duet runs on Claude Opus 5.5",
    "You can't watch Claude Duet work in its browser or take over the browser",
    "It checks your accounts at set intervals, so something urgent can arrive between checks",
    "it can read your work in Claude but can't change it",
    "It doesn't make phone calls or send text messages to other people",
    "With your approval, it can send emails from the accounts you've connected",
    "Microsoft 365 isn't available yet",
    "During the research preview, Claude Duet is included with the Pro and Max plans at no extra cost",
    "including the five-hour session and weekly limits",
    "Work it does in the background, like the morning brief and check-ins, also counts, so you may reach your limits sooner than with chat alone",
    "you get one full limit reset, which resets both your five-hour session and weekly limits",
    "This limit reset is available until November 30, 2026",
    "that content can contain instructions meant to mislead it. This is called prompt injection",
    "no defense is perfect, which is one reason consequential actions need your approval",
    "you type it into a separate form on your device",
    "each purchase uses a one-time card that only works for that purchase",
    "Link and Shop Pay are available only in Claude Duet for now",
    "Disconnecting an app stops Claude Duet from accessing it from that point on, but memory of past information from earlier conversations is kept",
    "only you can mark a task as completed",
    "If you can't approve right away, Claude Duet finishes the rest of the task and brings the approval back to you later",
    "It searches your Claude Duet chats and your chats in Claude outside of projects",
]
OPENAI = [
    "Powered by GPT-6 Astra, your dot lives in the cloud and has its own computer and browser",
    "even when your computer is off",
    "open its computer and select Take over",
    "Return control",
    "You reach the same dot in ChatGPT, Slack, Teams, or a call",
    "Pro 100, Pro 200, and Pro 500: For users over 18 outside the European Economic Area, United Kingdom, and Switzerland",
    "Business Premium: Rolling out worldwide",
    "Enterprise: Rolling out worldwide. Dots are off by default and must be enabled by a workspace administrator",
    "Dots are rolling out gradually to eligible accounts",
]
statements = {"announcement": {s: has(T["announcement"], s) for s in ANNOUNCEMENT}, "help_article": {s: has(T["help"], s) for s in HELP},
              "openai_dots_docs": {s: has(T["openai_dots"], s) for s in OPENAI}}
missing = {k: [s for s, ok in v.items() if not ok] for k, v in statements.items()}

# ---- plan prices Duet is included in -------------------------------------------------------------------------------------
data_plan = sorted({(m.group(1), m.group(2) or "", m.group(3).strip()) for m in
                    re.finditer(r'data-plan="([^"]+)"(?:\s+data-plan-field="([^"]+)")?[^>]*>([^<]*)<', raw["pricing"]) if m.group(3).strip()})
plans = {"pro_monthly": next((t for p, f, t in data_plan if p == "pro_monthly"), None),
         "pro_annual_per_month": next((t for p, f, t in data_plan if p == "pro_annual" and f == "amount_per_month"), None),
         "max_5x_monthly": next((t for p, f, t in data_plan if p == "max_5x_monthly"), None),
         "pricing_page_mentions_claude_duet": "Claude Duet" in T["pricing"]}

# ---- where the press differs from Anthropic's pages -----------------------------------------------------------------------
eng = T["engadget"]
m = re.search(r"Notably, Anthropic says subscribers of its \$20 per month Pro plan will get access once the agent rolls out in general availability[^.]*\.", eng)
press = {
    "macrumors_says_like_muse_and_dots_duet_has_a_virtual_machine_with_its_own_browser": has(T["macrumors"], "As with Muse and Dots, Duet has a virtual machine with its own browser"),
    "macrumors_says_limited_to_pro_and_max_in_the_us": "limited to Pro and Max subscribers in the United States" in T["macrumors"],
    "engadget_pro_sentence": m.group(0) if m else None,
    "engadget_says_dots_only_on_openai_pro_tier_starting_at_100_a_month": "Dots, which are currently only available to OpenAI's Pro tier subscribers. Those plans start at $100 per month" in eng,
    "unite_says_runs_on_opus_5_5_and_checks_every_few_hours": has(T["unite"], "Claude Opus 5.5") and has(T["unite"], "every few hours"),
}
conflicts = {"anthropic_pages_say_pro_and_max_both_eligible_for_the_waitlist_now": has(T["help"], "users on the Pro and Max plans in the US, through a waitlist"),
             "engadget_says_pro_gets_access_only_once_general_availability": bool(m)}

# ---- connectors named on the help page -----------------------------------------------------------------------------------------
named = [n for n in ("Gmail", "Google Calendar", "Google Drive", "Slack", "QuickBooks", "HubSpot", "Docusign", "Calendly") if n in T["help"]]
announcement_apps = [n for n in ("Gmail", "Slack", "Intuit QuickBooks", "Stripe", "Gusto", "LinkedIn", "Docusign", "HubSpot", "Canva", "Shopify", "Link", "Shop Pay", "1Password") if n in T["announcement"]]

json.dump({"as_of": AS_OF, "sources": URLS, "statements": statements, "statements_not_found": missing,
           "statement_counts": {k: {"found": sum(v.values()), "checked": len(v)} for k, v in statements.items()}, "plans_duet_is_included_in": plans,
           "connectors_named_on_help_page": named, "apps_named_in_announcement": announcement_apps, "press_wording": press, "press_vs_anthropic": conflicts},
          sys.stdout, indent=2, sort_keys=True)
sys.stdout.write("\n")
