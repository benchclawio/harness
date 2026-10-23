# Ollama and nine alternatives: public-record read, 2026-10-23

Evidence for https://benchclaw.io/ollama-alternatives/. A static read of public GitHub, PyPI and vendor records. No package was installed or run, no account was used,
no model was called, nothing was billed. BenchClaw makes no claim about how fast or good any of these tools is.

## What it reads

- GitHub for eight repositories (Ollama as the baseline; Jan, llama.cpp, vLLM, LocalAI, GPT4All, text-generation-webui, Atomic Chat): licence (SPDX, and the licence file at the
  repository root), archived flag, canonical name, last commit before the cut-off, latest stable release, stable releases in the 90 days before the cut-off, tagged releases
  including pre-releases, GitHub's own "latest release" marker, published security advisories (followed by cursor, deduplicated by GHSA id) and README sentences.
- LM Studio: its app terms (Element Labs, Inc.) and the licences of the repositories in the lmstudio-ai GitHub organisation.
- Ollama: its pricing page, its context-length documentation, and `llama/README.md` in its repository.
- Msty's pricing page. Atomic Chat's and XDA's own "Ollama alternatives" articles.
- PyPI for vLLM and GPT4All: latest stable version, upload date, versions in 90 days.
- Google's AI Overview for "ollama alternatives" (saved text and cited sources), to check its claims.

An advisory count measures disclosure, not safety. Release counts are counts of tags or versions and say nothing about the size of a release. llama.cpp tags builds about a
dozen times a day, and GitHub marks most of those tags as pre-releases.

## Reproduce

```bash
export GITHUB_TOKEN=...   # optional; about 150 GitHub requests, the anonymous limit is 60 an hour
python3 check_ollama_alternatives.py --as-of 2026-10-23T14:30:00Z > out.json
```

Two runs on 2026-10-23 produced byte-identical output (see `run_twice.sh`). Versions, releases, commits and advisories are fixed by `--as-of`; page text is read live, so a later run
can differ. `reader_commands.sh` holds the six commands in the article's "check it yourself" section.

## Files

- `check_ollama_alternatives.py`, `ollama-alternatives-2026-10-23.json`, `google-ai-overview-ollama-alternatives-2026-10-23.md`
- `reader_commands.sh`, `run_twice.sh`, `commit_and_push.sh`

## Limits

We did not run any tool, so nothing here ranks them on speed, quality, privacy or platform support. GPT4All's licence file was not parsed (GitHub reports MIT). We read Msty's pricing
page and LM Studio's terms, not LM Studio's pricing, and we did not look for Msty's source. AnythingLLM, Open WebUI and KoboldCpp, named by other lists, were not read.
