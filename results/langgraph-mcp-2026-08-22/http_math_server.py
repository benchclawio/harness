from mcp.server.fastmcp import FastMCP


server = FastMCP("benchclaw-math", host="127.0.0.1", port=18765)


@server.tool()
def multiply(a: int, b: int) -> int:
    """Multiply two integers."""
    return a * b


if __name__ == "__main__":
    server.run(transport="streamable-http")

