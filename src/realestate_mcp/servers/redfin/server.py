"""MCP server for Redfin residential real-estate listings.

Redfin does not offer a public REST API. This server scrapes their
server-rendered pages and parses the embedded ReactServerAgent cache
(the __reactServerState.InitialContext JS variable). Use at your own
risk under Redfin's Terms of Service.

Only ZIP-code search is supported in MVP. For-sale status only.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import _client

mcp = FastMCP("redfin")

_PROXY = os.environ.get("REDFIN_PROXY_URL", "")


@mcp.tool()
async def search_homes(
    zip_code: str,
    status: str = "for_sale",
    min_beds: int = 0,
    max_beds: int = 0,
    min_price: int = 0,
    max_price: int = 0,
    max_results: int = 50,
) -> dict[str, Any]:
    """Search Redfin for-sale listings in a ZIP code.

    Returns a dict with `search_area`, `total_returned`, and `homes`.
    Each home: listing_id, url, address, city, state, zip, price (USD float
    or null), bedrooms (int or null), bathrooms (float or null, halves
    included), building_sqft (int or null), lot_sqft (int or null),
    year_built (int or null), image_url.

    Only `status="for_sale"` (the default) is supported in MVP. Other
    values are accepted but the result set will still reflect for-sale
    listings — the ZIP page defaults to active for-sale.

    Args:
        zip_code: 5-digit US ZIP code (e.g. "28704").
        status: Listing status filter — "for_sale" only in MVP.
        min_beds: Minimum bedroom count; 0 = any.
        max_beds: Maximum bedroom count; 0 = any.
        min_price: Minimum list price in USD; 0 = unset.
        max_price: Maximum list price in USD; 0 = unset.
        max_results: Cap on returned listings (default 50, max ~199 per page).
    """
    return await asyncio.to_thread(
        _client.search_homes,
        zip_code,
        status=status,
        min_beds=min_beds,
        max_beds=max_beds,
        min_price=min_price,
        max_price=max_price,
        max_results=max_results,
        proxy_url=_PROXY,
    )


@mcp.tool()
async def get_home_details(
    home_url_or_id: str,
) -> dict[str, Any]:
    """Fetch full details for a single Redfin listing.

    Returns a dict with: listing_id, url, address, city, state, zip,
    price, bedrooms, bathrooms, building_sqft, lot_sqft, year_built,
    description, image_urls (list), listing_agent, listing_brokerage,
    days_on_market, hoa_fee (always null in MVP — not reliably available
    on the detail page without an additional authenticated API call).

    Args:
        home_url_or_id: Full redfin.com URL (e.g.
            "https://www.redfin.com/NC/Arden/732-Streamside-Dr-28704/home/111190110")
            OR a bare numeric property ID (e.g. "111190110" or 111190110).
            Full URLs are more reliable — bare IDs attempt a /home/<id> redirect
            which may not resolve for off-market properties.
    """
    return await asyncio.to_thread(
        _client.get_home_details,
        home_url_or_id,
        proxy_url=_PROXY,
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
