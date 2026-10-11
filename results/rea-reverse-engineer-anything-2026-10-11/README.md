# REA (morluto/rea): static read, 2026-10-11

Evidence for the BenchClaw article [REA Reverse Engineer Anything: What It Installs, and What We Verified](https://benchclaw.io/rea-reverse-engineer-anything/).

**REA was not installed, imported or run, and nothing was analysed with it.** The script reads public records only.

## What this checks

The GitHub repository and its latest release tag (`rea-agents-6.4.0`): `install.sh`, `package.json`, `SECURITY.md`, `README.md`, `docs/installation.md`, `.gitmodules` and the licences of the five submodules; the npm registry record for `rea-agents` (versions and publish times, install hooks, dependencies, provenance attestation); and the text of 17 U.S.C. 1201(f) from Cornell's Legal Information Institute, the exception for reverse engineering done for interoperability.

## Method

- `check_rea.py`: Python standard library only. About 25 GitHub requests, so set `GITHUB_TOKEN` (unauthenticated GitHub allows 60 an hour). Dates use a fixed cut-off, `--as-of 2026-10-11T18:00:00Z`. Two runs on 2026-10-11 were byte-identical.
- Star and fork counts change every minute, so they are not in the JSON. The article quotes them with their read time (96,069 stars, 21,430 forks at 2026-10-11 18:06 UTC from the GitHub API).
- Text checks are phrase matches on the file text at the release tag, with whitespace normalised.
- `rea-2026-10-11.json`: the raw, unedited output.

## Limits

This is a read of what the project says and ships. It does not test whether REA works, whether its tools are safe on a hostile binary, or what the 1,161 files in the npm package do beyond what the manifest and the documentation state. `SECURITY.md` says REA is not a sandbox. Nothing here is legal advice.

## Reproduce

```bash
export GITHUB_TOKEN=...   # any read-only token
python3 check_rea.py > mine.json     # about 20 seconds
```
