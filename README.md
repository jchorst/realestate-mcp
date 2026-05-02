# realestate-mcp

MCP servers for real-estate web service "APIs" — Python 3.14, uv-managed.

The four target services don't expose usable public REST APIs for indie developers, so each server scrapes the corresponding site's server-rendered pages and parses embedded JSON. See `AGENTS.md` for the full layout, conventions, and per-service quirks.

## Status

| Service | Entry point     | Status                                                                 |
| ------- | --------------- | ---------------------------------------------------------------------- |
| Airbnb  | `airbnb-mcp`    | Implemented — `search_stays`, `get_listing_details`                    |
| LoopNet | `loopnet-mcp`   | Stub (ping only)                                                       |
| Vrbo    | `vrbo-mcp`      | Stub (ping only)                                                       |
| Zillow  | `zillow-mcp`    | Stub (ping only)                                                       |

## Develop

```sh
uv sync                    # install + create .venv
uv run pytest -q           # 78 tests, ~1s, all mocked
uv run ruff check .
uv run airbnb-mcp          # run the Airbnb MCP server over stdio
```

## Use with Claude Code

```bat
setup.bat       :: install all servers as uv tools, register implemented ones with Claude Code
teardown.bat    :: unregister and uninstall
```

## Layout

```
src/realestate_mcp/servers/<service>/
  _client.py    sync; HTTP + parse
  server.py     FastMCP tools (async, wraps _client via asyncio.to_thread)
tests/
  test_<service>_helpers.py     pure helper tests
  test_<service>_parsers.py     JSON parsers w/ minimal hand-crafted fixtures
  test_<service>_search.py      mocked-HTTP integration
.claude/agents/    five focused sub-agents (see AGENTS.md)
AGENTS.md          project conventions, gotchas, sub-agent index
```

## Caveats

Each service's TOS forbids scraping. This project is for personal use; commercial resale of scraped data is a different conversation. Schemas drift — when a parser breaks, the `airbnb-schema-doctor` sub-agent is the intended repair workflow.
