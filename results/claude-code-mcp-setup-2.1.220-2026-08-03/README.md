# Claude Code MCP setup verification

This evidence checks the MCP configuration commands used in BenchClaw's
`Claude Code MCP Servers` guide against Claude Code 2.1.220.

The verifier uses an isolated `CLAUDE_CONFIG_DIR`, a temporary project and a
harmless local MCP server. It checks local and project scopes, stdio and HTTP
registration, health reporting, listing and removal. The Playwright and
Context7 entries are registered but not started or authenticated, so this is a
configuration-surface test rather than a service or performance benchmark.

Run:

```bash
node verify_claude_code_mcp_setup.mjs
```

The published JSON is deterministic across five executions. Temporary test
directories contain configuration only and no credentials.

