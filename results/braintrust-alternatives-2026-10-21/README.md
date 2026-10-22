# Braintrust and ten open-source alternatives: public-record read, 2026-10-21

Evidence for https://benchclaw.io/braintrust-alternatives/. A static read of public GitHub, PyPI and npm records, licence files and vendor pages.
No package was installed or run, no account was used, no model was called, nothing was billed. BenchClaw makes no claim about how well any of
these tools evaluates anything.

## What it reads

- Braintrust: its pricing page (Starter, Pro and Enterprise lines), its self-hosting documentation (data plane and control plane), the title and text of its own
  "Braintrust alternatives" article, and the licences of the repositories in its GitHub organisation.
- GitHub for ten alternatives (Langfuse, Arize Phoenix, Opik, MLflow, W&B Weave, LangWatch, Laminar, DeepEval, Promptfoo, Ragas): licence (SPDX, and the root `LICENSE`
  file where one exists), archived flag, description, last commit before the cut-off, latest stable release, stable releases in the 90 days before the cut-off,
  published security advisories, and README sentences about ownership or maintenance.
- PyPI (npm for Promptfoo): latest stable version, upload date, versions in 90 days.
- The ClickHouse and Langfuse announcements of the January 2026 Langfuse acquisition, and Promptfoo's announcement that it is joining OpenAI.
- Google's AI Overview for "braintrust alternatives" (saved text), to check its claims.

An advisory count measures disclosure, not safety. Release counts are counts of tags or versions, and say nothing about the size of a release.

## Reproduce

```bash
export GITHUB_TOKEN=...   # optional; about 70 GitHub requests, the anonymous limit is 60 an hour
python3 check_braintrust_alternatives.py --as-of 2026-10-21T19:30:00Z > out.json
```

Two runs on 2026-10-22 produced byte-identical output (sha256 `17da5b88...4b4edf`, see `run_twice.sh`). Versions, releases, commits and advisories are
fixed by `--as-of`; page text is read live, so a later run can differ.

## Files

- `check_braintrust_alternatives.py`, `braintrust-alternatives-2026-10-21.json`, `google-ai-overview-braintrust-alternatives-2026-10-21.md`
- `reader_commands.sh` (the five commands in the article's "check it yourself" section), `run_twice.sh`, `commit_and_push.sh`

## Limits

MLflow, LangWatch, Laminar and DeepEval have no `LICENSE` file at the repository root path we tried, so for them only GitHub's reported licence is recorded.
We did not read Braintrust's Enterprise terms or any closed alternative (LangSmith, Galileo, Datadog). We found no repository for Braintrust's platform in the
organisation repositories we read, which is not proof that none exists.
