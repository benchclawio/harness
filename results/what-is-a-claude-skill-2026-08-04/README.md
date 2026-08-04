# Progressive disclosure in Agent Skills — measurement

Supporting evidence for <https://benchclaw.io/what-is-a-claude-skill/>.

Every page ranking for "what is a claude skill" — including Google's AI Overview —
asserts that progressive disclosure saves context. None publishes a figure.

A token count requires Anthropic's tokenizer, and an estimated token count is not a
measurement. What is exactly measurable offline, with no model call, is the **proportion**
of a Skill that is always loaded (YAML frontmatter `name` + `description`) against the
proportion that stays on disk until the Skill is triggered.

## Reproduce

```bash
python3 measure_skill_disclosure.py <skills-dir> [<skills-dir> ...]
```

Point it at any directory of Skill folders containing `SKILL.md`, for example
`~/.claude/skills`.

## Result, 2026-08-04

51 production Skills using the `SKILL.md` convention:

| Measure | Result |
| --- | --- |
| Always-loaded metadata | 4,953 bytes |
| Total `SKILL.md` content | 140,728 bytes |
| Total bundled content | 248,930 bytes |
| Always-loaded share of bundle | 1.99% |
| Median Skill's always-loaded share | 3.30% |
| Deferred until triggered | 98.01% |

Full output: `skill-disclosure-measurement-2026-08-04.txt`.

The aggregate hides the useful part: the ratio depends on how much a Skill bundles. A
single-file Skill of 813 bytes defers 21.89% of itself; the largest Skill in this set
bundles 35,865 bytes and defers 99.73%. Progressive disclosure pays off through bundled
resources, not through having Skills at all.

## Method notes

- Deterministic: the script reads files and counts bytes, with no model in the loop.
  Executed three times on 2026-08-04 with byte-identical output.
- Bytes are a proxy for tokens, not a substitute. The ratio transfers; absolute token
  cost depends on the tokenizer.
- Anthropic's own figures (~100 tokens of metadata per Skill, under 5k tokens of
  instructions when triggered) are cited from their Agent Skills documentation as
  published 2026-08-04. They are not our measurements.
