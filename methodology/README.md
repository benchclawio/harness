# Methodology addenda

The methodology core lives at https://benchclaw.io/methodology/. Each content cluster adds
an addendum that states what a benchmark in that cluster measures, what it controls for,
and what it explicitly does not claim.

| Cluster | Addendum | Location |
| --- | --- | --- |
| One — agent frameworks | agent-frameworks v0.1.0 | published with the framework benchmark bundles under `results/` |
| Two — agent tooling | agent-tooling v0.1.0 | `results/herdr-0.8.0-vs-tmux-2026-08-07/agent-tooling-methodology-v0.1.0.md` |
| Three — observability and evaluation tooling | observability v0.1.0 | `methodology/observability-methodology-v0.1.0.md` |

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
