# Methodology addenda

The methodology core lives at https://benchclaw.io/methodology/. Each content cluster adds
an addendum that states what a benchmark in that cluster measures, what it controls for,
and what it explicitly does not claim.

| Cluster | Addendum | Location |
| --- | --- | --- |
| One — agent frameworks | agent-frameworks v0.1.0 | published with the framework benchmark bundles under `results/` |
| Two — agent tooling | agent-tooling v0.1.0 | `results/herdr-0.8.0-vs-tmux-2026-08-07/agent-tooling-methodology-v0.1.0.md` |
| Three — observability and evaluation tooling | observability v0.1.0 | `methodology/observability-methodology-v0.1.0.md` |
| Three — evaluation subclass | observability v0.2.0 | `methodology/observability-methodology-v0.2.0.md` |

## Why cluster three's addendum is published here rather than in a results bundle

Clusters one and two published their addenda alongside the first benchmark that used them.
That is tidy, but it means the addendum and the results carry the same timestamp, so the
claim "we fixed the protocol before we saw the data" cannot be checked by anyone outside
the project.

Cluster three's addendum is committed **before any measurement in that cluster exists**.
The commit date is the pre-registration. When the first observability benchmark publishes,
its bundle will reference this file rather than restate it, and the ordering will be
verifiable from the repository history.

Later clusters should follow this pattern.

## v0.2.0 and the bc-038 pre-registration

v0.1.0 defines one primary outcome for cluster three: capture completeness, whether an
instrument records what the application did. The Langfuse and Phoenix benchmark under
`results/llm-observability-langfuse-phoenix-2026-08-12/` measured exactly that and returned
a null result.

That outcome does not fit tools that **judge** output rather than record it. An evaluator
can capture everything perfectly and still call a wrong answer correct. v0.2.0 adds
evaluator agreement as a second primary outcome for that subclass, headlined by the
false-pass rate, and leaves v0.1.0 untouched for capture runs.

Committed alongside it, and for the same pre-registration reason, are the two files that
fix the next benchmark before it runs:

- `bc038-corpus-spec-v0.1.0.md` — the six defect classes, the per-class case counts, and
  the labelling procedure, including the rule that arguable cases are discarded rather than
  resolved.
- `bc038-workload-v0.1.0.json` — the 60 induction tasks whose outputs become the corpus,
  generated deterministically by `scripts/bc038_workload.py`.

**No measurement exists at this commit.** No evaluator has been installed and no run has
been executed. The point of publishing the workload now is that a reader can check we did
not choose the defect classes after seeing which ones the tools happened to miss.
