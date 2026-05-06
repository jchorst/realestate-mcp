# AGENTS.md

Real-estate MCP servers — Python 3.14, uv-managed. Each MCP server wraps a different real-estate web service so an LLM agent can search/inspect listings.

## Quickstart

```sh
uv sync                       # install + create .venv (idempotent)
uv run pytest -q              # full test suite (~1s, all mocked)
uv run ruff check .           # lint
uv run black src tests        # format
uv run airbnb-mcp             # run Airbnb MCP server over stdio
```

Per-server entry points are declared in `pyproject.toml` under `[project.scripts]`: `airbnb-mcp`, `carolinadesigns-mcp`, `loopnet-mcp`, `sunrealty-mcp`, `surforsound-mcp`, `twiddy-mcp`.

## Layout

```
src/realestate_mcp/servers/
├── airbnb/            implemented — search + listing details via embedded-JSON scraping
├── carolinadesigns/   implemented — direct JSON API (Drupal Solr-backed) for OBX north
├── twiddy/            implemented — direct JSON API for OBX north
├── surforsound/       implemented — HTML scrape (BeautifulSoup) for OBX Hatteras Island
├── sunrealty/         implemented — Solr search + HTML detail; per-week pricing gated
└── loopnet/           stub (ping only)

tests/
├── test_<service>_helpers.py    pure-function tests
├── test_<service>_parsers.py    parsers w/ minimal hand-crafted fixtures
├── test_<service>_search.py     mocked-HTTP integration
└── test_smoke.py                module-import smoke tests
```

## Conventions

- **HTTP**: scrapers use `curl_cffi.requests` with `impersonate="chrome124"`. Do not swap to `httpx` for scrapers — Airbnb fingerprints TLS handshakes and rejects non-browser clients, and most other scraping targets do too.
- **Async boundary**: `_client.py` is sync; `server.py` wraps every call in `asyncio.to_thread`. Fan out parallel calls (e.g. `check_in_dates`) at the server layer with `asyncio.gather`.
- **Schema drift is loud**: parsers raise `RuntimeError("Unexpected <service> response shape: ...")` when a top-level structural key is missing. Do not silence this with `try/except` — it's the canary.
- **Defensive on optional fields**: use `.get()` chains and default to `None`/`[]` so a single missing optional field doesn't crash the whole listing.
- **Tests mock at the HTTP layer**: monkeypatch `_client.requests.get` directly. `respx` is in deps but is httpx-only — it won't intercept curl-cffi.
- **No comments unless they explain a non-obvious WHY** (a workaround, an upstream quirk, a hidden invariant). Type hints + names should explain the WHAT.
- `from __future__ import annotations` at the top of every module.
- Line length 100 (black + ruff configured).

## Real-estate API reality

None of the broad-market consumer services offer usable public REST APIs for indie developers:

| Service | Reality |
|---|---|
| Airbnb | Official program invite-only; we scrape server-rendered search/PDP pages. |
| LoopNet / CoStar | Enterprise contracts only; no developer access. |
| Vrbo | Akamai-protected; would need Playwright. Evaluated and dropped. |
| Zillow | PerimeterX/CloudFront blocks `curl_cffi` impersonation outright. Attempted, removed; would need a residential proxy or Playwright. |

OBX-specific local property managers (Carolina Designs, Twiddy, Surf or Sound, Sun Realty) are different — most expose internal JSON APIs (Solr, Bluetent, Drupal CMS endpoints) that respond fine to `curl_cffi` with no auth. The OBX MCPs lean on those.

Each service's TOS forbids scraping. This is a personal-use project; commercial resale of scraped data is a different conversation.

## Airbnb-specific gotchas

The Airbnb parser walks two JSON paths embedded in `<script id="data-deferred-state-0" type="application/json">`:

- **Search** (`/s/<city>/homes?...`): `niobeClientData[0][1].data.presentation.staysSearch.results.searchResults`
- **PDP** (`/rooms/<id>?...`): `niobeClientData[0][1].data.presentation.stayProductDetailPage.sections.sections` (a list keyed by `sectionId`)

Section IDs we depend on for the PDP: `TITLE_DEFAULT`, `DESCRIPTION_DEFAULT`, `AMENITIES_DEFAULT`, `MEET_YOUR_HOST`, `REVIEWS_DEFAULT`, `LOCATION_DEFAULT`, `POLICIES_DEFAULT`, `BOOK_IT_SIDEBAR`, `SLEEPING_ARRANGEMENT_WITH_IMAGES`, `HIGHLIGHTS_DEFAULT`, `HERO_DEFAULT`.

Known quirks (don't "fix" these without checking):

- `propertyId` at the top level of a search result is always `null`. Decode the base64 `demandStayListing.id` (e.g. `RGVtYW5kU3RheUxpc3Rpbmc6MjM3Mzk3NDE=` → `DemandStayListing:23739741`) and split on `:`.
- When the search URL carries `price_min`/`price_max`, Airbnb truncates `structuredContent.primaryLine` and drops bath info. We filter price client-side after fetching.
- `node.pdpPresentation.mediaTour.stops` is empty when the PDP URL has no dates. Fall back to `HERO_DEFAULT.previewImages[*].baseUrl` for photos.
- `_structured_field(sc, "bed")` would match `"3 bedrooms"`. Use `exclude="bedroom"` for beds. (Caught by `test_airbnb_helpers.py` — keep that test.)

## Adding a new service

Follow the Airbnb shape:

1. `src/realestate_mcp/servers/<service>/_client.py` — sync; dataclasses for slim outputs; `_parse_*` functions take dict, return dataclass; raise `RuntimeError` on shape drift.
2. `src/realestate_mcp/servers/<service>/server.py` — `mcp = FastMCP("<service>")`; each tool wraps `asyncio.to_thread(_client.<func>, ...)`.
3. `tests/test_<service>_{helpers,parsers,search}.py` — same three-layer split.
4. Add the entry point to `[project.scripts]` in `pyproject.toml` (already present for the four stubs).
5. Run `uv sync && uv run ruff check . && uv run pytest -q` before declaring done.

## Environment

- `AIRBNB_PROXY_URL` — optional; passes through to `curl_cffi` for residential-proxy use under heavy load. Light personal use doesn't need it.

## Sub-agents (`.claude/agents/`)

Five focused sub-agents are available for routine workflows. Each has hard rules to prevent common pitfalls; read the agent file before invoking manually.

| Agent | Use when |
|---|---|
| `airbnb-schema-doctor` | Airbnb parser raises `Unexpected response shape`, returns empty fields, or produces nonsense values. Reproduces live → narrow patch → mirror in fixture → verify. |
| `mcp-service-bootstrapper` | Starting work on a stub service (LoopNet) or adding a new one (e.g. another OBX local manager). Scaffolds `_client.py`, `server.py`, and the three test files following the Airbnb pattern. |
| `python-reviewer` | Reviewing uncommitted changes against project conventions before commit. Read-only; produces a severity-categorized punch list. |
| `test-author` | Adding test coverage for new/modified code. Picks the right test layer (helpers / parsers / mocked-HTTP), reuses existing builder helpers, never records real-response fixtures. |
| `test-mender` | `pytest` is failing. Classifies each failure by root cause and fixes at the right layer. Will not weaken assertions, skip, or delete tests to hit a passing run. |
