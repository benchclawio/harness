#!/usr/bin/env python3
"""Measure how many input tokens Claude Code sends before it has done any work.

Four configurations, each run RUNS times, one call per run, no retries:
  A  empty project, no CLAUDE.md, no MCP server
  B  A + a generated CLAUDE.md of about 2,000 words
  C  A + a stdio MCP server exposing 10 tools
  D  A + a stdio MCP server exposing 40 tools

The prompt is always "Reply with the single word OK." Token counts are the
`usage` object the Anthropic API returns through `claude -p --output-format
stream-json`; nothing is estimated with a tokenizer. Total input tokens =
input_tokens + cache_creation_input_tokens + cache_read_input_tokens.

Standard library only. Needs the `claude` CLI logged in. Writes one JSON file.
Usage: python3 measure_fixed_context.py [--runs 3] [--model claude-haiku-4-5-20251001] --out result.json
"""
import argparse, json, os, shutil, subprocess, sys, tempfile, datetime

MODEL = "claude-haiku-4-5-20251001"
PROMPT = "Reply with the single word OK."


def claude_md_text(words=2000):
    """Deterministic, plain-English project conventions, about `words` words."""
    topics = [
        "Name every function after what it returns, not how it computes it.",
        "Keep each module under four hundred lines and split it when it grows.",
        "Write a failing test before fixing a reported bug, then fix the bug.",
        "Never catch an exception unless the handler adds information or recovers.",
        "Prefer plain data structures to classes until behaviour needs to travel with the data.",
        "Log one line per external call with the duration and the status code.",
        "Pin every dependency to an exact version and record the date it was checked.",
        "Review diffs for unrelated changes before committing and split them out.",
        "Document the reason for a decision in the commit message, not only the change.",
        "Delete dead code instead of commenting it out because history keeps it.",
    ]
    out, n, i = [], 0, 0
    while n < words:
        line = f"{i + 1}. " + topics[i % len(topics)] + f" (rule {i + 1})"
        out.append(line)
        n += len(line.split())
        i += 1
    return "# Project conventions\n\n" + "\n".join(out) + "\n"


MCP_SERVER = r'''#!/usr/bin/env python3
import json, sys
N = int(sys.argv[1])
TOOLS = [{
    "name": f"lookup_record_{i:02d}",
    "description": f"Look up record type {i:02d} by identifier and return its fields as JSON.",
    "inputSchema": {"type": "object", "properties": {
        "identifier": {"type": "string", "description": "Identifier of the record to fetch."},
        "fields": {"type": "array", "items": {"type": "string"}, "description": "Optional field names to return."},
        "include_history": {"type": "boolean", "description": "Include the change history."}},
        "required": ["identifier"]}} for i in range(N)]
for line in sys.stdin:
    try: msg = json.loads(line)
    except Exception: continue
    mid, method = msg.get("id"), msg.get("method")
    if method == "initialize":
        res = {"protocolVersion": msg["params"].get("protocolVersion", "2024-11-05"),
               "capabilities": {"tools": {}}, "serverInfo": {"name": "fixture", "version": "1.0"}}
    elif method == "tools/list":
        res = {"tools": TOOLS}
    elif method == "tools/call":
        res = {"content": [{"type": "text", "text": "{}"}]}
    elif method == "ping":
        res = {}
    else:
        if mid is None: continue
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "n/a"}}) + "\n"); sys.stdout.flush(); continue
    if mid is not None:
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": mid, "result": res}) + "\n"); sys.stdout.flush()
'''


def build(cfg, root):
    proj = os.path.join(root, "proj")
    os.makedirs(proj)
    mcp = {"mcpServers": {}}
    if cfg == "B":
        open(os.path.join(proj, "CLAUDE.md"), "w").write(claude_md_text())
    if cfg in ("C", "D"):
        srv = os.path.join(root, "fixture_mcp.py")
        open(srv, "w").write(MCP_SERVER)
        n = "10" if cfg == "C" else "40"
        mcp["mcpServers"]["fixture"] = {"command": sys.executable, "args": [srv, n]}
    mcp_path = os.path.join(root, "mcp.json")
    json.dump(mcp, open(mcp_path, "w"))
    return proj, mcp_path


def one_call(cfg, model):
    root = tempfile.mkdtemp(prefix=f"ctxeng-{cfg}-")
    try:
        proj, mcp_path = build(cfg, root)
        cmd = ["claude", "-p", PROMPT, "--model", model, "--output-format", "stream-json", "--verbose",
               "--no-session-persistence", "--setting-sources", "project", "--disable-slash-commands",
               "--strict-mcp-config", "--mcp-config", mcp_path]
        p = subprocess.run(cmd, cwd=proj, capture_output=True, text=True, timeout=240)
        init, result, usages = None, None, []
        for line in p.stdout.splitlines():
            try: o = json.loads(line)
            except Exception: continue
            if o.get("type") == "system" and o.get("subtype") == "init": init = o
            if o.get("type") == "assistant" and isinstance(o.get("message"), dict) and o["message"].get("usage"):
                usages.append(o["message"]["usage"])
            if o.get("type") == "result": result = o
        if not usages:
            return {"config": cfg, "error": "no usage in output", "returncode": p.returncode, "stderr_tail": p.stderr[-300:]}
        u = usages[-1]
        tot = u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0)
        return {"config": cfg, "total_input_tokens": tot, "input_tokens": u.get("input_tokens", 0),
                "cache_creation_input_tokens": u.get("cache_creation_input_tokens", 0),
                "cache_read_input_tokens": u.get("cache_read_input_tokens", 0),
                "output_tokens": u.get("output_tokens", 0), "api_calls": len(usages),
                "reply": (result or {}).get("result"),
                "tools_in_init": sorted(init.get("tools", [])) if init else None,
                "mcp_servers_in_init": init.get("mcp_servers") if init else None,
                "model_in_init": init.get("model") if init else None}
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--configs", default="ABCD")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    ver = subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.strip()
    runs = []
    for cfg in a.configs:
        for r in range(a.runs):
            res = one_call(cfg, a.model)
            res["run"] = r + 1
            runs.append(res)
            print(cfg, r + 1, res.get("total_input_tokens"), res.get("error", ""), flush=True)
            if "error" in res:
                break  # one attempt per run; stop this config on the first error, never retry
    json.dump({"date_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d"), "claude_code_version": ver,
               "model": a.model, "prompt": PROMPT, "runs_per_config": a.runs, "runs": runs},
              open(a.out, "w"), indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
