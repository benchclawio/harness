# A2A protocol: public-record read, 2026-10-21

Evidence for https://benchclaw.io/a2a-protocol/. A static read of the A2A specification site, GitHub, PyPI and npm records. No package was
installed or run, no agent was started, no account was used, no model was called, nothing was billed. BenchClaw makes no claim about whether
any A2A implementation works or interoperates.

## What it reads

- The specification site (a2a-protocol.org): the latest and previous released versions, the protocol-binding sections, the breaking-change notes in "What's New in
  v1.0", the version-negotiation header, and the 27 August 2026 announcement that A2A joined the Agentic AI Foundation.
- GitHub for the specification repository, the Python, JavaScript, Java, Go and .NET SDK repositories, and IBM's Agent Communication Protocol repository:
  licence, archived flag, creation date, last commit, latest stable release (and recent history), releases in the last 90 days, published security advisories.
- PyPI and npm for the Python and JavaScript SDKs: version, date, downloads for the last month.
- PyPI metadata (declared dependencies and extras, never installed) of 17 agent-framework packages, to see which declare an A2A dependency or extra and
  which `a2a-sdk` versions they allow.
- Google's AI Overview for "a2a protocol" (saved text), to check its claims.

Downloads include automated installs and installs pulled in by other packages. An advisory count measures disclosure, not safety.

## Reproduce

```bash
export GITHUB_TOKEN=...   # optional; about 50 GitHub requests, the anonymous limit is 60 an hour
python3 check_a2a_protocol.py --as-of 2026-10-21T19:00:00Z > out.json
```

Two runs on 2026-10-21 produced byte-identical output (sha256 `50671333...5f5186`, see `run_twice.sh`). Versions, uploads, commits and advisories are
fixed by `--as-of`; download counts are the trailing month at read time, and the specification site and announcement are read live, so a later
run can differ.

## Files

- `check_a2a_protocol.py`, `a2a-protocol-2026-10-21.json`, `google-ai-overview-a2a-protocol-2026-10-21.md`
- `reader_commands.sh` (the four commands in the article's "check it yourself" section), `run_twice.sh`, `commit_and_push.sh`

## Limits

We did not run any A2A agent or test interoperability, including a 0.3 SDK against a 1.x one. The announcement's adoption figures (over 150 organizations,
cloud-provider support) are the project's own and were not verified. We found no A2A dependency for LangGraph although the announcement names it. We did
not read the Rust SDK the specification site lists.
