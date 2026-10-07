#!/usr/bin/env python3
"""Summarise raw-A.json and raw-BCD.json from measure_fixed_context.py. Standard library only."""
import json, subprocess, sys, statistics, importlib.util, os

here = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("m", os.path.join(here, "measure_fixed_context.py"))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
runs = json.load(open(os.path.join(here, "raw-A.json")))["runs"] + json.load(open(os.path.join(here, "raw-BCD.json")))["runs"]
meta = json.load(open(os.path.join(here, "raw-BCD.json")))
out = {"claude_code_version": meta["claude_code_version"], "model": meta["model"], "date_utc": meta["date_utc"], "configs": {}}
for c in "ABCD":
    t = [r["total_input_tokens"] for r in runs if r["config"] == c]
    n_tools = len([r for r in runs if r["config"] == c][0]["tools_in_init"])
    out["configs"][c] = {"runs": len(t), "totals": t, "mean": round(statistics.mean(t), 1), "spread": max(t) - min(t), "tools_listed_at_start": n_tools}
base = out["configs"]["A"]["mean"]
for c in "BCD":
    out["configs"][c]["added_over_A"] = round(out["configs"][c]["mean"] - base, 1)
words = len(m.claude_md_text().split())
out["claude_md_words"] = words
out["tokens_per_claude_md_word"] = round(out["configs"]["B"]["added_over_A"] / words, 3)


def tools_json_bytes(n):
    inp = "\n".join(json.dumps(x) for x in [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}},
                                             {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}]) + "\n"
    p = subprocess.run([sys.executable, "-c", m.MCP_SERVER, str(n)], input=inp, capture_output=True, text=True)
    return len(json.dumps(json.loads(p.stdout.splitlines()[1])["result"]["tools"], separators=(",", ":")).encode())


for c, n in (("C", 10), ("D", 40)):
    out["configs"][c]["mcp_tools"] = n
    out["configs"][c]["full_definition_json_bytes"] = tools_json_bytes(n)
    out["configs"][c]["added_tokens_per_tool"] = round(out["configs"][c]["added_over_A"] / n, 1)
out["added_tokens_per_extra_tool_C_to_D"] = round((out["configs"]["D"]["mean"] - out["configs"]["C"]["mean"]) / 30, 1)
print(json.dumps(out, indent=2, sort_keys=True))
