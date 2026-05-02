from mcp.server.fastmcp import FastMCP

mcp = FastMCP("loopnet")


@mcp.tool()
async def ping() -> str:
    return "loopnet-mcp: ok"


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
