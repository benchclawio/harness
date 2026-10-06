# LangGraph alternatives: framework snapshot (bc-104)

Evidence for the BenchClaw article [LangGraph Alternatives: What to Use Instead, and When](https://benchclaw.io/langgraph-alternatives/).

## What this checks

Release and maintenance metadata for LangGraph and eleven other agent frameworks, read on
2026-10-06: latest stable version, days since it was released, stable releases in the last 90
days, first stable release, licence, required Python, and whether the repository is archived.
It also checks each repository README for the words "maintenance mode" and for a pointer to
Microsoft Agent Framework.

## Method

- `check_framework_snapshot.py`: standard library only, no API key, nothing installed. One
  PyPI JSON request, one unauthenticated GitHub REST request and one raw README request per
  project, sequential, no retries. Run twice on 2026-10-06; the two outputs were byte-identical.
- `framework-snapshot-2026-10-06.json`: the raw, unedited output.

## Limits

This is metadata, not a measurement of how any framework behaves. Release counts say how
often a project ships, not whether the releases are good. Package names matter: `pydantic-ai-slim`,
`llama-index-core`, `autogen-agentchat` and `agent-framework` are the packages named in the
JSON, and the ecosystems around them are larger. Some PyPI licence fields are empty, so the
GitHub licence field is recorded beside them; GitHub reports AutoGen's repository as CC-BY-4.0
because of its documentation licence, while its package is MIT. The measured head-to-heads quoted in the
article come from earlier BenchClaw runs with their own evidence directories, not from this script.

## Result (2026-10-06)

- LangGraph 1.2.13 was released a day before the read; 5 stable releases in 90 days.
- Microsoft Agent Framework 1.20.0 (first stable PyPI release 2026-04-02) is MIT-licensed.
- The AutoGen README states "AutoGen is now in maintenance mode" and recommends Microsoft Agent
  Framework for new projects; its last PyPI release was 371 days before the read.
- The Semantic Kernel README states it is now Microsoft Agent Framework.
- smolagents' last PyPI release (1.26.0, 2026-05-29) was 130 days before the read, while its repository
  was pushed to on the day of the read.
