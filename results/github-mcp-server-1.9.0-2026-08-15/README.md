# GitHub MCP Server 1.9.0 deterministic checks

BenchClaw downloaded the official Linux x86_64 release archive, matched its SHA-256 digest to
GitHub's release-asset metadata, and ran the zero-secret checks in `verify.mjs` on 2026-08-15.

The verifier repeats the version, read-only scope-inventory, configuration-parser and documented
`tool-search` probes five times and requires identical process output. `evidence.json` records the
result. No credential, authenticated GitHub request, hosted MCP call or model call was used.

Run it against the official release archive and extracted binary:

```text
node verify.mjs /path/to/github-mcp-server_Linux_x86_64.tar.gz /path/to/github-mcp-server
```
