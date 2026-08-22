from mcp.server.fastmcp import FastMCP


server = FastMCP("benchclaw-math")


@server.tool()
def multiply(a: int, b: int) -> int:
    """Multiply two integers."""
    return a * b


if __name__ == "__main__":
    server.run(transport="stdio")

