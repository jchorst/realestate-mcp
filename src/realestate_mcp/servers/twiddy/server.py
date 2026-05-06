"""MCP server for Twiddy & Company vacation rental search.

Twiddy manages 1,000+ Outer Banks NC vacation rentals, concentrated in
Corolla (including the 4x4-only beach area), Duck, and Southern Shores.
This server exposes their internal web-api (endpoints are public in their
JS bundle) to enable search by town and retrieval of property details
including weekly availability and pricing.
"""

from __future__ import annotations

import asyncio
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import _client

mcp = FastMCP("twiddy")


@mcp.tool()
async def search_rentals(
    town: str,
    min_bedrooms: int = 0,
    max_results: int = 50,
) -> dict[str, Any]:
    """Search Twiddy & Company vacation rentals by OBX town.

    Returns a dict with `search_area`, `total_returned`, and `listings`.
    Each listing has: listing_id, url, name, bedrooms, bathrooms (None at
    search scope — use get_rental_details for split full/half counts), town,
    neighborhood, distance_to_beach, image_url, oceanfront, sleeps.

    pet_friendly and private_pool are not populated here; use
    get_rental_details to retrieve amenity data for a specific property.

    Per-week pricing is not included in search results. Use
    get_rental_details to obtain weekly rates for a specific property.

    Args:
        town: One of: corolla, duck, southern-shores, kill-devil-hills,
              nags-head, 4x4. The "4x4" area is the remote beach north of
              Corolla reachable only by 4WD vehicle.
        min_bedrooms: Minimum bedroom count; 0 = any.
        max_results: Cap on returned listings (default 50).
    """
    return await asyncio.to_thread(
        _client.search_rentals,
        town=town,
        min_bedrooms=min_bedrooms,
        max_results=max_results,
    )


@mcp.tool()
async def get_rental_details(rental_url_or_id: str) -> dict[str, Any]:
    """Fetch full details for a single Twiddy rental property.

    Returns a dict with: listing_id, url, name, town, neighborhood,
    bedrooms, bathrooms_full, bathrooms_half, sleeps, description,
    amenities, image_urls, weekly_rates.

    weekly_rates is a list of {arrive, depart, weekly_rate, is_available,
    week_content} for each week in the current booking season. Entries where
    is_available is false are already booked.

    amenities is the list of featured amenities including "Pets Allowed"
    and "Private Pool" when applicable.

    Args:
        rental_url_or_id: Numeric property ID (e.g. "5744") or a full
            Twiddy URL (e.g.
            "https://www.twiddy.com/outer-banks/corolla/pine-island/rentals/station-one/").
    """
    return await asyncio.to_thread(_client.get_rental_details, rental_url_or_id)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
