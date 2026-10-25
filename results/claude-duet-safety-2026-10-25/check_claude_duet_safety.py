#!/usr/bin/env python3
"""Read what Anthropic documents about Claude Duet's safety, and the independent test of the classifier it builds on. Prints one JSON document.

Standard library only, no account, no waitlist signup, nothing billed, no model called, and Claude Duet itself is never run. Reads:
  - Anthropic's "Claude Duet Safety, Privacy, and Security" (claude.com/resources/articles/claude-duet-safety-privacy-and-security), dated 2026-10-23
  - Anthropic's launch announcement (2026-10-21), to see whether it still promises safety detail "in the coming days" and what it said about the classifier
  - Anthropic's help article "Get started with Claude Duet" (memory and disconnect wording)
  - Anthropic's "Use Claude Cowork safely" help article, which Google's AI Overview cites for Duet
  - Embrace The Red's "Breaking Claude Code Opus 5 Auto Mode" (2026-08-26): the attack-success table and the 0.00% evaluation it cites
  - google-ai-overview-is-claude-duet-safe-2026-10-25.md, saved next to this script, to check what Google's answer cites and leaves out

Each entry in "statements" is a sentence or phrase copied from a page; the value says whether that exact text (quotes normalised) is on the page today. Pages are read
live, so a later run can differ. --as-of is a label, not a filter.

Usage: python3 check_claude_duet_safety.py [--as-of 2026-10-25] > out.json
"""
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36", "Accept-Language": "en-US,en;q=0.9"}
HERE = os.path.dirname(os.path.abspath(__file__))
AS_OF = sys.argv[sys.argv.index("--as-of") + 1] if "--as-of" in sys.argv else "2026-10-25"


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
    t = t.replace(" (opens in new tab)", "")   # screen-reader text Anthropic adds inside every external link
    t = t.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace(" ", " ")
    t = re.sub(r"\s+", " ", t).strip()
    return re.sub(r" ([,.;:!?])", r"\1", t)


def has(text, phrase):
    return phrase.replace("’", "'") in text


URLS = {"safety_post": "https://claude.com/resources/articles/claude-duet-safety-privacy-and-security",
        "announcement": "https://claude.com/resources/articles/claude-duet",
        "help": "https://support.claude.com/en/articles/17631495-get-started-with-claude-duet",
        "cowork_safely": "https://support.claude.com/en/articles/13364135-use-claude-cowork-safely",
        "embrace": "https://embracethered.com/blog/posts/2026/breaking-claude-code-opus-5-and-automode/"}
raw = {k: must(u) for k, u in URLS.items()}
T = {k: flat(v) for k, v in raw.items()}

SAFETY = [
    "Date October 23, 2026",
    "Claude Duet is an agent, currently in research preview, that uses a cloud-based computer to do work for you",
    "it runs continuously even after you close the app",
    "a new classifier that checks messages Claude Duet drafts before they go out",
    "Claude Duet never sees your passwords, browser cookies, sign-in tokens, or other credentials",
    "it shows you the action, the destination, and the content, including every recipient",
    "built on the auto mode classifier from Claude Code and extended for Claude Duet",
    "The check runs outside the model doing the work so instructions hidden in a page cannot affect the outcome",
    "Some actions stay off-limits even with your approval, like trading securities, banking actions such as moving money between accounts, and accessing someone else's account",
    "like paying or sending money, deleting an order, or creating an account",
    "The routines that run while you are away have the same safeguards",
    "Approval fatigue is a serious issue",
    "We will continue to adjust this calibration over time",
    "a one-time card from a wallet like Link from Stripe, limited to that merchant and amount",
    "a new safety classifier that runs separately from the main model",
    "We categorize this information into two tiers",
    "We give the most sensitive protection to information like sign-in credentials, full card and bank account numbers, and government ID numbers",
    "Claude Duet is instructed never to share these with anyone, even if you ask",
    "Claude Duet will share other private information, such as health or finances, only if you've explicitly approved it",
    "Your own request counts as consent",
    "it can decide to rewrite the message without the sensitive information and share with you for approval",
    "these safeguards will occasionally miss something or flag a harmless message",
    "You can see what Claude Duet has done and is doing in its task list",
    "Claude Duet keeps your conversation history and its memory so it can carry context between tasks, until you delete your history or reset it",
    "Deleting your account wipes everything Claude Duet has stored",
    "what Claude Duet already learned from it stays until you reset its memory, which you can do anytime from the app's settings",
    "switching an app off in one place switches it off in both",
    "Claude Duet also uses the memory from your Claude account, so details Claude remembered from your earlier chats are visible",
    "The form encrypts it with a single-use key that exists only on our secure cloud browser machine",
    "The model doesn't see the password and can't save or repeat it",
    "Soon you will also be able to sign in with 1Password",
    "the sign-in form is itself a target",
    "It never arrives as a link, a text message, an email, or a website other than claude.ai",
    "A placeholder for the credential sits there instead and a proxy outside that machine puts in the real value only as a request is made",
    "Your browser in Claude Duet runs in its own dedicated virtual machine in the cloud",
    "The agent drives the browser only through a fixed set of commands",
    "What does come back is the page's text and downloads",
    "Files it uploads through the browser get the same sensitive-information check as its messages",
    "requests that its web browser sends include a distinct User-Agent header, and we publish the public IP addresses it browses from",
    "we also contacted several large websites and gave them the option to prevent Claude Duet from visiting their sites, and some chose to",
    "Our Safeguards team built evaluations from routine-shaped tasks, each in three variants: an innocent version, one with injected instructions, and one that tempts the agent to do more than it was asked",
    "An external penetration-testing firm tested Claude Duet with access to our source code, and a follow-on engagement covering the cloud browser and the sign-in form is running now",
    "Each new credential feature is red-teamed on an isolated rig before it ships to anyone",
    "Claude Duet is also in scope of Anthropic's public bug bounty program",
    "Some of what's described here is still changing: how often it asks for approval, how you sign in, and how well the sensitive-information checks tell what's private from what's harmless",
]
ANNOUNCEMENT = [
    "Actions are approved by our auto mode classifier, the same safeguard that protects Claude and Claude Code from taking steps you didn't ask for",
    "Red teams and an external firm penetration tested Claude Duet, and it's covered by our public bug bounty program",
    "reject requests to share the strictest tier of information, including credit card numbers and government identification",
    "will share more details about how Claude Duet is designed for safety in the coming days",
]
HELP = [
    "no defense is perfect, which is one reason consequential actions need your approval",
    "Disconnecting an app stops Claude Duet from accessing it from that point on, but memory of past information from earlier conversations is kept",
]
EMBRACE = [
    "Posted on Aug 26, 2026",
    "a third-party evaluation commissioned by Anthropic showed a 0.00% prompt injection attack success rate for Opus 5 in Auto Mode",
    "Auto Mode replaces human approval prompts with a safety classifier",
    "Since mid-August it is the default starting mode for Claude Code",
    "Auto Mode IS NOT a substitute for running your agent in an isolated environment and monitoring what it is up to",
    "They hired a vendor (Trajectory Labs) to test 72 indirect prompt injection scenarios ten times each",
    "These are small samples, not a universal ASR measurement",
    "The classifier allowed the creation of the malware process, but then it blocked the command intended to stop it",
    "Auto Mode only sees Claude's short Python catalogue decoder. The actual exploit was several hops away",
]
statements = {"safety_post": {s: has(T["safety_post"], s) for s in SAFETY}, "announcement": {s: has(T["announcement"], s) for s in ANNOUNCEMENT},
              "help_article": {s: has(T["help"], s) for s in HELP}, "embrace_the_red": {s: has(T["embrace"], s) for s in EMBRACE}}
missing = {k: [s for s, ok in v.items() if not ok] for k, v in statements.items()}

# ---- what the safety post does not contain ---------------------------------------------------------------------------------
sp = T["safety_post"]
absences = {
    "percent_signs_in_safety_post": sp.count("%"),
    "mentions_success_rate": bool(re.search(r"success rate", sp, re.I)),
    "mentions_false_positive_or_false_negative": bool(re.search(r"false (?:positive|negative)", sp, re.I)),
    "mentions_penetration_test_findings_or_results": bool(re.search(r"penetration[- ]test(?:ing)? (?:results|findings|report)", sp, re.I)),
    "names_the_penetration_testing_firm": bool(re.search(r"penetration-testing firm (?:called|named)|Trail of Bits|NCC Group|Cure53", sp)),
    "mentions_constitutional_ai": "Constitutional AI" in sp or "constitutional" in sp.lower(),
    "mentions_any_independent_test_of_duet": bool(re.search(r"independent(?:ly)? (?:test|evaluat|audit)", sp, re.I)),
    "the_word_Trajectory_appears": "Trajectory" in sp,
}

# ---- the Embrace The Red table ------------------------------------------------------------------------------------------------
table = re.findall(r"(python3 -I -c \(C2 chain\)|claude -p subprocess)\s+(.+?)\s+(\d/\d \(\d+%\))", T["embrace"])
embrace_rows = [{"variant": v, "effects": re.sub(r"\( ", "(", re.sub(r" \)", ")", e.strip())), "asr": a} for v, e, a in table]
embrace = {"table_rows": embrace_rows, "product_tested": "Claude Code" if "Claude Code Opus 5 in Auto Mode" in T["embrace"] or "Claude Code Opus 5 Auto Mode" in T["embrace"] else None,
           "mentions_claude_duet": "Duet" in T["embrace"]}

# ---- Google's AI Overview -------------------------------------------------------------------------------------------------------
aio_text = open(os.path.join(HERE, "google-ai-overview-is-claude-duet-safe-2026-10-25.md"), encoding="utf-8").read()
overview_part = aio_text.split("## Sources cited by the overview")[0]
refs_part = aio_text.split("## Sources cited by the overview")[1].split("## Organic results")[0]
organic_part = aio_text.split("## Organic results")[1].split("## People also ask")[0]
cow = T["cowork_safely"]
aio = {
    "cites_cowork_safety_article": "support.claude.com/en/articles/13364135-use-claude-cowork-safely" in refs_part,
    "cowork_article_title_is_use_claude_cowork_safely": "Use Claude Cowork safely" in cow,
    "cowork_article_mentions_duet": "Duet" in cow,
    "cites_the_oct_23_duet_safety_post": "claude-duet-safety-privacy-and-security" in refs_part,
    "cited_domains_in_reference_list": sorted({m.group(1) for m in re.finditer(r"^- (\S+) ", refs_part, re.M)}),
    # The reference list holds three entries, but the overview text carries more inline citation links; count those too.
    "inline_citation_urls": sorted({u.split("&t=")[0] for u in re.findall(r"\]\((https?://[^)\s]+)\)", overview_part)}),
    "inline_citation_url_count": len({u.split("&t=")[0] for u in re.findall(r"\]\((https?://[^)\s]+)\)", overview_part)}),
    "any_inline_citation_url_contains_duet": any("duet" in u.lower() for u in re.findall(r"\]\((https?://[^)\s]+)\)", overview_part)),
    "overview_mentions_constitutional_ai": "Constitutional AI" in overview_part,
    "overview_mentions_classifier": "classifier" in overview_part.lower(),
    "overview_mentions_penetration_test": "penetration" in overview_part.lower(),
    "overview_mentions_credentials_never_seen": bool(re.search(r"password|credential|sign-in", overview_part, re.I)),
    "overview_says_isolated_cloud_environments": "isolated cloud environments" in overview_part,
    "overview_says_research_preview_for_pro_and_max": "research preview" in overview_part.lower() and "Pro and Max" in overview_part,
    "any_organic_result_is_the_oct_23_duet_safety_post": "claude-duet-safety-privacy-and-security" in organic_part,
    "organic_result_count": len(re.findall(r"^\d+\. ", organic_part, re.M)),
}

json.dump({"as_of": AS_OF, "sources": URLS, "statements": statements, "statements_not_found": missing,
           "statement_counts": {k: {"found": sum(v.values()), "checked": len(v)} for k, v in statements.items()},
           "safety_post_absences": absences, "embrace_the_red": embrace, "ai_overview_checks": aio},
          sys.stdout, indent=2, sort_keys=True)
sys.stdout.write("\n")
