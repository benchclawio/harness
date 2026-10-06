# LangSmith alternatives (bc-108)

Evidence for the BenchClaw article [LangSmith Alternatives: What to Use Instead, With the Cost Arithmetic](https://benchclaw.io/langsmith-alternatives/).

## What this checks

Release cadence, licence, activity and declared OpenTelemetry dependency for LangSmith's SDK and
nine alternatives, read on 2026-10-06 from PyPI, GitHub and each README.

## Method

- `check_observability_snapshot.py`: standard library only, no API key, nothing installed. One PyPI
  JSON request, one unauthenticated GitHub REST request and one raw README request per project,
  sequential, no retries. Run twice on 2026-10-06; the two outputs were byte-identical. It makes about ten
  GitHub API requests; GitHub allows 60 an hour per IP address unauthenticated. An optional `GITHUB_TOKEN`
  environment variable lifts that limit and is used only for `api.github.com` reads of public data; the
  outputs here were produced with one set.
- `observability-snapshot-2026-10-06.json`: the raw, unedited output.
- Pricing arithmetic for LangSmith and Langfuse is not repeated here; it comes from
  `results/langsmith-pricing-2026-10-04` and `results/langfuse-pricing-2026-10-05`.
- `google-ai-overview-langsmith-alternatives-2026-10-06.md`: Google's AI Overview text for the query.

## Limits

This is metadata, not a measurement of tracing quality. A declared OpenTelemetry dependency is a
proxy for OpenTelemetry-based instrumentation, not proof of it. The GitHub licence field describes
the repository named in the JSON, which for LangSmith and Braintrust is the client SDK and not the
hosted platform. Release counts show how often a project ships, not whether the releases are good.
Measured results quoted in the article come from earlier BenchClaw runs with their own evidence directories.

## Result (2026-10-06)

- Phoenix's PyPI licence is Elastic-2.0; Langfuse's repository reports NOASSERTION because parts
  are separately licensed; MLflow, Opik, Laminar and OpenLLMetry are Apache-2.0.
- LangSmith's SDK declares no OpenTelemetry dependency; Langfuse, Phoenix, Laminar and OpenLLMetry do.
