# Claude Duet safety: public-record read, 2026-10-25

Evidence for https://benchclaw.io/is-claude-duet-safe/. A static read of Anthropic's published pages about Claude Duet, one independent security write-up of the classifier Duet's
action check is built on, and Google's AI Overview for the query. Claude Duet was never run, no account or waitlist signup was used, no model was called, nothing was billed.
BenchClaw makes no claim about how well any Duet safeguard works.

## What it reads

- Anthropic, "Claude Duet Safety, Privacy, and Security" (dated 2026-10-23): 45 exact statements, and whether it contains percent signs, a success rate, test findings, the
  penetration-testing firm's name, a false-positive or false-negative rate, or any mention of an independent test.
- Anthropic's launch announcement (2026-10-21): the "auto mode classifier" sentence, the penetration-test sentence, the strictest-tier sentence and the promise of safety detail
  "in the coming days".
- Anthropic's help article "Get started with Claude Duet": the prompt-injection and disconnect/memory sentences.
- Anthropic's help article "Use Claude Cowork safely", which Google's AI Overview links: its title, and whether it mentions Duet.
- Embrace The Red, "Breaking Claude Code Opus 5 Auto Mode" (2026-08-26): the attack-success table (3/5, 3/5, 4/5), the 0.00% evaluation it cites, and its own caveats.
- Google's AI Overview for "is claude duet safe" (saved text, inline citation links, organic results), to check what it cites and leaves out.

## Reproduce

```bash
python3 check_claude_duet_safety.py --as-of 2026-10-25 > out.json
```

Two runs on 2026-10-25 produced byte-identical output (see `run_twice.sh`). Pages are read live, so a later run can differ; `--as-of` is a label, not a filter.
`reader_commands.sh` holds the four commands in the article's "check it yourself" section.

## Files

- `check_claude_duet_safety.py`, `claude-duet-safety-2026-10-25.json`, `google-ai-overview-is-claude-duet-safe-2026-10-25.md`
- `reader_commands.sh`, `run_twice.sh`, `commit_and_push.sh`

## Limits

We did not read the Anthropic-commissioned evaluation itself (Trajectory Labs); its numbers are as Embrace The Red describes them. The Cloud Security Alliance note on the same
test could not be fetched (HTTP 403) and is not used. Embrace tested Claude Code with Opus 5, not Duet. We found no independent test of Duet.
