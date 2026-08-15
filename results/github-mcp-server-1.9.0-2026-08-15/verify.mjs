#!/usr/bin/env node

import crypto from "node:crypto";
import fs from "node:fs";
import { spawnSync } from "node:child_process";

const [archivePath, binaryPath] = process.argv.slice(2);
if (!archivePath || !binaryPath) {
  console.error("Usage: verify.mjs ARCHIVE BINARY");
  process.exit(2);
}

const expectedSha256 = "cbf38bd3364518ccf80b6a25587d5ef11655b15d63cbb48bc066384d0b5b5964";
const repeats = 5;
const configs = [
  {
    servers: {
      github: {
        type: "http",
        url: "https://api.githubcopilot.com/mcp/",
      },
    },
  },
  {
    mcpServers: {
      github: {
        command: "docker",
        args: [
          "run",
          "-i",
          "--rm",
          "-e",
          "GITHUB_PERSONAL_ACCESS_TOKEN",
          "ghcr.io/github/github-mcp-server",
          "--read-only",
          "--toolsets=repos,issues,pull_requests",
        ],
        env: {
          GITHUB_PERSONAL_ACCESS_TOKEN: "${env:GITHUB_PERSONAL_ACCESS_TOKEN}",
        },
      },
    },
  },
];

function run(args) {
  return spawnSync(binaryPath, args, { encoding: "utf8" });
}

function repeatProbe(args) {
  const runs = Array.from({ length: repeats }, () => run(args));
  const signatures = runs.map(({ status, stdout, stderr }) =>
    JSON.stringify({ status, stdout, stderr }),
  );
  if (new Set(signatures).size !== 1) {
    throw new Error(`Non-deterministic output for: ${args.join(" ")}`);
  }
  return runs[0];
}

const archiveSha256 = crypto
  .createHash("sha256")
  .update(fs.readFileSync(archivePath))
  .digest("hex");
if (archiveSha256 !== expectedSha256) {
  throw new Error(`Checksum mismatch: ${archiveSha256}`);
}

for (const config of configs) {
  for (let i = 0; i < repeats; i += 1) JSON.parse(JSON.stringify(config));
}

const version = repeatProbe(["--version"]);
const scopes = repeatProbe([
  "--read-only",
  "--toolsets=repos,issues,pull_requests",
  "list-scopes",
  "--output=summary",
]);
const toolSearch = repeatProbe(["tool-search", "issue", "--max-results", "5"]);

if (version.status !== 0 || !version.stdout.includes("Version: 1.9.0")) {
  throw new Error(`Unexpected version output: ${version.stdout}${version.stderr}`);
}
if (scopes.status !== 0 || !scopes.stdout.includes("repo")) {
  throw new Error(`Unexpected scope output: ${scopes.stdout}${scopes.stderr}`);
}
if (toolSearch.status === 0 || !toolSearch.stderr.includes("unknown command")) {
  throw new Error("Expected v1.9.0 to reject the documented tool-search command");
}

console.log(JSON.stringify({
  checked_on: "2026-08-15",
  release: "1.9.0",
  repeats,
  archive_sha256: archiveSha256,
  version_output: version.stdout.trim(),
  read_only_scope_output: scopes.stdout.trim(),
  config_shapes_parsed: ["remote_http_oauth", "local_docker_pat_reference"],
  tool_search_probe: {
    exit_code: toolSearch.status,
    stderr: toolSearch.stderr.trim(),
  },
  boundaries: [
    "No GitHub credential was used",
    "No authenticated GitHub API or MCP tool call was made",
    "No hosted endpoint latency or reliability was measured",
  ],
}, null, 2));
