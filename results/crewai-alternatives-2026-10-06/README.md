# CrewAI alternatives (bc-105)

Evidence for the BenchClaw article [CrewAI Alternatives: What to Use Instead, and What to Check First](https://benchclaw.io/crewai-alternatives/).

## What this checks

1. The CrewAI dependency blocker: whether `chromadb` is a core requirement of the latest `crewai`
   release, ChromaDB's latest release, and the GitHub security advisory GHSA-f4j7-r4q5-qw2c
   (affected range and first patched version).
2. How often the READMEs of CrewAI, ten alternatives and OpenAI Swarm use the words
   "multi-agent", "handoff", "team" and "role", plus whether the Swarm README says it was replaced.

## Method

- `check_crewai_alternatives.py`: standard library only, no API key, nothing installed. PyPI JSON,
  the GitHub advisory API and raw READMEs, one request each, sequential, no retries. Run twice on
  2026-10-06; the two outputs were byte-identical.
- `crewai-alternatives-2026-10-06.json`: the raw, unedited output.
- `google-ai-overview-crewai-alternatives-2026-10-06.md`: Google's AI Overview text for the query, from one live SERP call.

## Limits

README word counts show what a project says about itself, not what it does, and a README is not
a feature list. We did not install CrewAI, ChromaDB or any alternative, so we did not test whether
the advisory is reachable in a given deployment. The advisory's own page is the authority on
exposure. Release and maintenance data for the alternatives is in
`results/langgraph-alternatives-2026-10-06`.

## Result (2026-10-06)

- `crewai` 1.15.23 requires `chromadb~=1.1.0` as a core dependency, not an extra.
- ChromaDB's latest release is 1.5.9 (2026-05-05). GHSA-f4j7-r4q5-qw2c (CVE-2026-45829, critical,
  pre-authentication code injection) affects `>= 1.0.0, <= 1.5.9` and lists no patched version.
- CrewAI's README says "role" 14 times; none of the ten alternatives uses it more than 0 times,
  except OpenAI Swarm (5). The OpenAI Swarm README says it is replaced by the OpenAI Agents SDK.
