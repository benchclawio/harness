#!/usr/bin/env python3
"""How many input tokens did the first model call of each Claude Code session carry?

Reads Claude Code session transcripts (default ~/.claude/projects/*/*.jsonl), takes the first
non-sidechain assistant message that has a `usage` object (skipping `<synthetic>` messages),
and sums input_tokens + cache_creation_input_tokens + cache_read_input_tokens. That is the
whole prompt the model received on its first call: system prompt, tool list, CLAUDE.md,
memory, hooks output and the user's first message. It prints counts and percentiles only;
no transcript text, paths or session ids are written to the output.

Standard library only. Usage: python3 first_turn_context_from_logs.py [projects_dir]
"""
import glob, json, os, sys, collections

root = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/.claude/projects")
totals, versions, models = [], collections.Counter(), collections.Counter()
for f in sorted(glob.glob(os.path.join(root, "*", "*.jsonl"))):
    ver = None
    for line in open(f, errors="ignore"):
        try:
            o = json.loads(line)
        except Exception:
            continue
        if o.get("isSidechain"):
            continue
        ver = ver or o.get("version")
        m = o.get("message") if isinstance(o.get("message"), dict) else None
        if o.get("type") == "assistant" and m and m.get("usage") and m.get("model") != "<synthetic>":
            u = m["usage"]
            totals.append(u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0))
            versions[ver] += 1
            models[m.get("model")] += 1
            break


def pct(s, p):
    return s[min(len(s) - 1, int(round(p * (len(s) - 1))))]


s = sorted(totals)
buckets = collections.OrderedDict((k, 0) for k in ("under_20k", "20k_to_40k", "40k_to_60k", "60k_to_100k", "over_100k"))
for t in s:
    k = "under_20k" if t < 20000 else "20k_to_40k" if t < 40000 else "40k_to_60k" if t < 60000 else "60k_to_100k" if t < 100000 else "over_100k"
    buckets[k] += 1
print(json.dumps({"sessions": len(s), "min": s[0], "p25": pct(s, .25), "median": pct(s, .5), "p75": pct(s, .75),
                  "max": s[-1], "buckets": buckets, "claude_code_versions": dict(sorted(versions.items(), key=lambda x: str(x[0]))),
                  "models": dict(sorted(models.items(), key=lambda x: str(x[0])))}, indent=2, sort_keys=True))
