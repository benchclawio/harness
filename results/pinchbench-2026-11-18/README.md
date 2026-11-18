# PinchBench source inspection — 18 November 2026

This is evidence for BenchClaw's PinchBench interpretation guide, not a benchmark run.
No package was installed, agent task executed, model API called or result uploaded.

## Source pins and observed boundaries

- Skill/tasks commit: `819384ae830492365b8363fc26bc2602e73f216d`.
- Official orchestration scripts commit: `92a27eca2f57af0194aa89ff4c9ea3d0e2ca2661`.
- Latest release returned by GitHub at inspection: v2.0.0, published 2026-05-06.
- README says 53 tasks. The official About catalogue says 147 across 11 categories.
  A single read-only tree inspection found 147 `tasks/task_*.md` files. Release notes
  advertise 148. This does not establish the exact suite behind any leaderboard row.
- Version file: 2.0.0. Manifest includes a core subset. Task selection matters.
- Runner aggregates task-level mean grades with partial credit; the repeat argument
  defaults to one. This is static source inspection, not a claim about official runs.
- Calendar task simulates calendar creation through an ICS file. It does not test a live
  calendar integration. Cities-ranking task declares automated/LLM weights 0.6/0.4.
- Judging descriptions differ among About, release notes and CLI help. No live run's
  effective judge backend or model was audited.

`source-records.json` contains source URLs, response hashes, bounded excerpts and static
observations; it intentionally does not republish full third-party pages or task files.
`collect-source-records.mjs` is the collector used locally. It fetches documentation/source
as inert text and never executes downloaded code. Its paths describe the BenchClaw local
workspace, not a standalone installation command. Run history: default collection completed;
an optional additional source lookup recorded one 404 for a guessed task-loader path and
stopped. That failed path supplies no article claim and was not retried.

Limits: no current model ranking validation, no production reliability measurement, no
security certification, no cost/invoice audit. The repository advisory endpoint returned
an empty list; that is not proof of absence of vulnerabilities. General web discovery was
unavailable, and the linked acquirer's page was bot-blocked; no acquisition claim is made.

Source licence: the inspected skill repository's LICENSE is MIT, copyright 2026 PinchBench.
See the pinned upstream licence for the underlying benchmark code.
