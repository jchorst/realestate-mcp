from mcp.server.fastmcp import FastMCP

mcp = FastMCP("vrbo")


@mcp.tool()
async def ping() -> str:
    return "vrbo-mcp: ok"


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
