"""MCP server for Sun Realty vacation rental search.

Sun Realty is the largest Outer Banks NC vacation rental property manager,
covering the entire OBX from Carova/4x4 Beaches through Hatteras village.
This server exposes their Solr API (search) and HTML detail pages (property
details) to enable search by town and retrieval of property information.
"""

from __future__ import annotations

import asyncio
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import _client

mcp = FastMCP("sunrealty")


@mcp.tool()
async def search_rentals(
    town: str,
    min_bedrooms: int = 0,
    max_results: int = 50,
    check_in: str = "",
) -> dict[str, Any]:
    """Search Sun Realty vacation rentals by OBX town.

    Returns a dict with `search_area`, `total_returned`, and `listings`.
    Each listing has: listing_id, url, name, bedrooms, bathrooms_full,
    bathrooms_half, sleeps, town, community, distance_to_beach,
    featured_amenities, image_url, check_in.

    Per-week pricing is not included. Use get_rental_details for
    availability windows on a specific property.

    Args:
        town: OBX town slug. Valid values: duck, corolla, kill-devil-hills,
              south-nags-head, nags-head, avon, kitty-hawk, salvo, carova,
              4x4, rodanthe, southern-shores, hatteras, waves, manteo.
        min_bedrooms: Minimum bedroom count; 0 = any.
        max_results: Cap on returned listings (default 50).
        check_in: Optional YYYY-MM-DD arrival date (stored on listings for
                  reference; does not filter availability in search results).
    """
    return await asyncio.to_thread(
        _client.search_rentals,
        town=town,
        min_bedrooms=min_bedrooms,
        max_results=max_results,
        check_in=check_in,
    )


@mcp.tool()
async def get_rental_details(rental_url_or_id: str) -> dict[str, Any]:
    """Fetch full details for a single Sun Realty rental property.

    Returns a dict with: listing_id, url, name, town, community, bedrooms,
    bathrooms_full, bathrooms_half, sleeps (None — not in HTML), description,
    amenities, image_urls, availability_windows.

    availability_windows is a list of {start, end, available} date ranges
    from the booking calendar embedded in the detail page.

    Args:
        rental_url_or_id: One of:
            - Numeric item_id string or int: "655" or 655
            - Property code: "SWB-36" or "swb-36"
            - Canonical URL: "https://www.sunrealtync.com/outer-banks/..."
    """
    return await asyncio.to_thread(_client.get_rental_details, rental_url_or_id)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
