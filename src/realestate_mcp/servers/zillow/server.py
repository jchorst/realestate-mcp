from mcp.server.fastmcp import FastMCP

mcp = FastMCP("zillow")


@mcp.tool()
async def ping() -> str:
    return "zillow-mcp: ok"


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
