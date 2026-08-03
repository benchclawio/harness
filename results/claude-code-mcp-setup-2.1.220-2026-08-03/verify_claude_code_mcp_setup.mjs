import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const mock = path.join(here, "mock_mcp_server.mjs");
const root = fs.mkdtempSync(path.join(os.tmpdir(), "benchclaw-claude-mcp-"));
const project = path.join(root, "project");
const config = path.join(root, "config");
fs.mkdirSync(project);
fs.mkdirSync(config);

const env = { ...process.env, CLAUDE_CONFIG_DIR: config };
const run = (args, options = {}) =>
  execFileSync("claude", args, {
    cwd: project,
    env,
    encoding: "utf8",
    timeout: 15000,
    ...options,
  });

const version = run(["--version"]).trim();
const addMock = run([
  "mcp",
  "add",
  "--scope",
  "local",
  "benchclaw-mock",
  "--",
  process.execPath,
  mock,
]);
const getMock = run(["mcp", "get", "benchclaw-mock"]);

const addPlaywright = run([
  "mcp",
  "add",
  "--scope",
  "project",
  "playwright",
  "--",
  "npx",
  "-y",
  "@playwright/mcp@0.0.78",
]);
const addContext7 = run([
  "mcp",
  "add",
  "--transport",
  "http",
  "--scope",
  "project",
  "context7",
  "https://mcp.context7.com/mcp",
]);

const list = run(["mcp", "list"], { timeout: 20000 });
const shared = JSON.parse(fs.readFileSync(path.join(project, ".mcp.json"), "utf8"));

run(["mcp", "remove", "--scope", "project", "context7"]);
run(["mcp", "remove", "--scope", "project", "playwright"]);
run(["mcp", "remove", "--scope", "local", "benchclaw-mock"]);

const remainingShared = fs.existsSync(path.join(project, ".mcp.json"))
  ? JSON.parse(fs.readFileSync(path.join(project, ".mcp.json"), "utf8"))
  : { mcpServers: {} };

const result = {
  claude_code_version: version.split(" ")[0],
  checked_at_utc: "2026-08-03",
  add_local_stdio: /Added stdio MCP server benchclaw-mock/.test(addMock),
  get_local_stdio_connected: /Status:.*Connected/s.test(getMock),
  add_project_stdio: /Added stdio MCP server playwright/.test(addPlaywright),
  add_project_http: /Added .*MCP server context7/i.test(addContext7),
  list_includes_all_three:
    list.includes("benchclaw-mock") && list.includes("playwright") && list.includes("context7"),
  project_file_has_playwright:
    shared.mcpServers?.playwright?.command === "npx" &&
    shared.mcpServers?.playwright?.args?.includes("@playwright/mcp@0.0.78"),
  project_file_has_context7:
    shared.mcpServers?.context7?.type === "http" &&
    shared.mcpServers?.context7?.url === "https://mcp.context7.com/mcp",
  removed_all_three: Object.keys(remainingShared.mcpServers ?? {}).length === 0,
  network_or_authentication_tested: false,
};

if (Object.entries(result).some(([key, value]) => key !== "network_or_authentication_tested" && !value)) {
  throw new Error(`Verification failed: ${JSON.stringify(result)}`);
}

process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
