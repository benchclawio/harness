# LangGraph MCP — executed examples

Supporting evidence for the BenchClaw `langgraph mcp` practical guide.

- Date: 2026-08-22 UTC
- Python: 3.12.13
- LangGraph: 1.2.11
- langchain-mcp-adapters: 0.3.2
- MCP SDK: 1.29.0 (the adapter requires `mcp>=1.24.0,<2.0.0`)
- Model calls: none
- Cost: $0

Both examples expose one `multiply(a, b)` MCP tool, discover it through
`MultiServerMCPClient`, convert it to a LangChain tool, execute it inside a LangGraph
`ToolNode`, and verify the result `42`.

`stdio_langgraph_mcp_example.py` passed 5/5 executions. The equivalent Streamable HTTP client
and server passed 5/5 executions. `results.json` records the application-level outputs.

The model node is scripted deliberately. These files test the MCP-to-LangGraph integration
without introducing a paid model, provider variance or prompt behaviour.

## Files

- `stdio_math_server.py` — local FastMCP stdio server.
- `stdio_langgraph_mcp_example.py` — current `MultiServerMCPClient` connection mapping and
  LangGraph `ToolNode`.
- `http_math_server.py` — localhost Streamable HTTP server.
- `http_langgraph_mcp_example.py` — equivalent HTTP connection.
- `results.json` — five deterministic results per transport plus version pins.

The MCP SDK emitted an `IncompleteFieldDefinitionWarning` from `pydantic_settings` when the
FastMCP process started. It did not prevent initialization, discovery, execution or clean exit.

