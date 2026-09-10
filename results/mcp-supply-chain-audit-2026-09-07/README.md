# MCP server package supply-chain audit

Evidence for the BenchClaw articles [MCP Server Security](https://benchclaw.io/mcp-server-security/)
and [AI Agent Security](https://benchclaw.io/ai-agent-security/).

## Method

The script makes read-only requests to the public npm registry. It searches for `mcp server`,
takes the first 100 registry-ranked results, filters to package names that identify an MCP
package, and records the latest release's registry signature, provenance attestation,
declared repository, licence and integrity algorithm.

It does not install, execute, connect to, fuzz or exploit any package.

## Files

- `audit_mcp_supply_chain.mjs` — dependency-free Node.js audit script.
- `mcp-supply-chain-audit-2026-09-07.json` — frozen 99-package snapshot used in the
  published article.
- `npm-key-verification-2026-09-07.json` — npm registry key response used to identify the
  common signing key.
- `staleness-recheck-2026-09-10.json` — later 100-package snapshot used to confirm that
  registry-ranked populations and package versions drift over time.

## Reproduce

From this directory, with Node.js 20 or newer:

```bash
node audit_mcp_supply_chain.mjs
```

The output filename includes the UTC date. Results will change as publishers release new
versions and npm's search ranking changes. Absence of provenance or a declared repository is
reported as absence of verifiability, not as a vulnerability or severity finding.
