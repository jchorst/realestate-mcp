---
name: check-mcp-drift
description: Run live smoke checks against every implemented MCP in this repo, surface any drift/breakage, and route fixes to the right workflow. Use when the user wants a maintenance pass on the MCP suite — for example "/check-mcp-drift", "are the MCPs still working?", "do a health check on the scrapers", or after a long gap since the last commit.
---

# Drift check for the realestate-mcp suite

## What this does

Runs `scripts/check_mcp_drift.py`, which exercises every implemented MCP's `search` + `get_details` paths against the live remote service and validates that a small set of required fields come back populated. The script reports per-MCP status (PASS / WARN / FAIL) and exits 1 when any FAIL is present.

Use this skill when the user wants a maintenance pass — to confirm none of the scrapers have silently broken since the last run.

## How to invoke

```
.venv\Scripts\python.exe scripts\check_mcp_drift.py
```

The script handles future-date computation (next Saturday ~2 months out) so it stays valid as time passes; no arguments needed.

## How to read the output

Per-MCP line shows `[+] PASS`, `[?] WARN`, or `[!] FAIL`. Below the table, the script prints detailed traces only for non-PASS results.

| Status | Meaning | Most likely cause |
|---|---|---|
| **PASS** | Search returned ≥1 result, all required fields populated; details for first result also populated. | Healthy. |
| **WARN** | Search returned 0 results. | Either real-world inventory drought OR drift. **Always investigate** by re-running the smoke spec with a broader query. |
| **FAIL** (search exception) | `search()` raised before any data came back. | Site-level issue: bot protection added (e.g. CloudFront 403, captcha), URL pattern changed, or DNS/network. |
| **FAIL** (search missing fields) | Search worked but the first result was missing a required field. | Schema drift on the listing-card / search-result level. |
| **FAIL** (details exception) | Details endpoint raised. | Detail page URL pattern changed, or detail-page bot protection added separately. |
| **FAIL** (details missing fields) | Detail call returned but key fields are empty. | Schema drift on the detail-page parser. |

## How to fix what you find

Workflows by failure mode:

1. **Site-level block (e.g. 403 on every URL).** Probe directly with `curl_cffi`:
   ```python
   from curl_cffi import requests
   r = requests.get("<the failing URL>", impersonate="chrome124", timeout=15)
   print(r.status_code, r.headers.get("Server"), r.text[:200])
   ```
   If the response shows `Akamai`, `PerimeterX`, `px-captcha`, or a CloudFront challenge: this MCP joins the "needs Playwright or residential proxy" tier. Document in AGENTS.md and consider removing per the Zillow precedent.

2. **Schema drift on a specific service.** For Airbnb specifically, delegate to the `airbnb-schema-doctor` agent — it's purpose-built for that workflow (reproduce live → narrow patch → mirror in fixture → verify). For other services, do the same loop manually:
   - Fetch the failing live page/endpoint and dump the raw response to `$env:TEMP\drift_<service>.{html,json}`.
   - Compare against the parser's expected selectors/keys.
   - Update the parser narrowly to match the new shape.
   - Update the corresponding hand-crafted fixture in `tests/test_<service>_parsers.py` so future drift will surface again.
   - Re-run `scripts/check_mcp_drift.py` to confirm green.

3. **Empty results / WARN.** First check whether the smoke spec's input is too narrow (e.g. `min_bedrooms=15` for a small inventory). If broadening the smoke recovers results, the MCP is healthy and the spec was just unlucky. Update the spec in `scripts/check_mcp_drift.py` to use safer defaults. If broadening doesn't recover results, treat it as drift.

## After fixing

- Re-run `scripts/check_mcp_drift.py` to confirm everything is back to PASS.
- Run `.venv\Scripts\python.exe -m pytest -q` to make sure no parser change broke a unit test.
- If a parser change shipped, propose a commit summarising what drifted and how. Don't push without explicit user approval.

## Where the smoke specs live

`scripts/check_mcp_drift.py` has one `_check_<service>()` function per MCP, each declaring:
- The search-call inputs.
- `search_required` — fields that must be populated on the first result.
- `details_required` — fields that must be populated on the detail call.
- `results_key` — the key holding the list of results in the search response (`listings`, `homes`, `properties`).

Adding coverage for a new MCP: append a new `_check_<service>()` function and add it to `CHECKS`. Match the input/required-fields shape used by the existing servers in the same domain.
