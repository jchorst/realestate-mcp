"""MCP server for Crexi commercial real estate search.

Crexi (https://www.crexi.com) is a major CRE listing platform. This server
wraps the public-ish JSON REST API at api.crexi.com. No auth token is required.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import _client

mcp = FastMCP("crexi")

_PROXY = os.environ.get("CREXI_PROXY_URL", "")


@mcp.tool()
async def search_properties(
    query: str,
    property_type: str = "",
    min_price: int = 0,
    max_price: int = 0,
    max_results: int = 50,
) -> dict[str, Any]:
    """Search Crexi for commercial real estate listings.

    Returns a dict with `search_query`, `total_returned`, and `properties`.
    Each property has: listing_id, url, name, address, city, state, zip,
    price, property_type, building_sqft, image_url.

    The Crexi API returns at most 50 results per query. Price and
    property_type filtering is applied client-side after the fetch.

    Tip: for churches and worship facilities, try queries like
    "church for sale", "worship center", or "religious facility".
    Crexi's Special Purpose and Land types most commonly match.

    Args:
        query: Free-text search term (required). E.g. "church", "warehouse",
               "medical office", "religious facility".
        property_type: Optional case-insensitive substring filter on the
               returned property_type field. E.g. "Special Purpose", "Land".
               Useful for narrowing the client-side result set.
        min_price: Minimum asking price in USD; 0 = unset.
        max_price: Maximum asking price in USD; 0 = unset.
        max_results: Cap on returned listings (default 50, max 50).
    """
    return await asyncio.to_thread(
        _client.search_properties,
        query,
        property_type=property_type,
        min_price=min_price,
        max_price=max_price,
        max_results=max_results,
        proxy_url=_PROXY,
    )


@mcp.tool()
async def get_property_details(
    listing_id_or_url: str,
) -> dict[str, Any]:
    """Fetch full details for a single Crexi listing.

    Returns a dict with: listing_id, url, name, address, city, state, zip,
    price, property_type, description, building_sqft, lot_acres, year_built,
    image_urls, broker_name, broker_phone.

    Notes:
    - broker_phone is not exposed by the public API (always null).
    - image_urls comes from a second API call to the gallery endpoint; it
      will be empty if the listing has no public gallery.
    - broker_name comes from a third API call; it may be null if the
      brokers endpoint requires auth or returns nothing.

    Args:
        listing_id_or_url: A Crexi asset ID (numeric, e.g. "12558") or a
               full URL like https://www.crexi.com/properties/{slug}/{id}.
               Use the listing_id from search_properties results.
    """
    return await asyncio.to_thread(
        _client.get_property_details,
        listing_id_or_url,
        proxy_url=_PROXY,
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
