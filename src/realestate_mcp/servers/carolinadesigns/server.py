"""MCP server for Carolina Designs Realty vacation rental search.

Carolina Designs manages 350+ Outer Banks NC vacation rentals. This server
exposes their internal website API (credentials are public in their JS bundle)
to enable search by town and retrieval of property details including weekly
availability and pricing.
"""

from __future__ import annotations

import asyncio
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import _client

mcp = FastMCP("carolinadesigns")


@mcp.tool()
async def search_rentals(
    town: str,
    min_bedrooms: int = 0,
    max_results: int = 50,
) -> dict[str, Any]:
    """Search Carolina Designs vacation rentals by town.

    Returns a dict with `search_area`, `total_returned`, and `listings`.
    Each listing has: listing_id, url, name, bedrooms, bathrooms_full,
    bathrooms_half, town, location, subdivision, image_url, pet_friendly,
    private_pool.

    Per-week pricing is not included in search results. Use
    get_rental_details to obtain weekly rates for a specific property.

    Args:
        town: One of: corolla, duck, southern-shores, kitty-hawk,
              kill-devil-hills, nags-head.
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
    """Fetch full details for a single Carolina Designs rental property.

    Returns a dict with: listing_id, url, name, town, bedrooms,
    bathrooms_full, bathrooms_half, sleeps, description, amenities,
    image_urls, weekly_rates, min_price, max_price.

    weekly_rates is a list of {arrival_date, weekly_rate, nightly_rate,
    book_type} for available Saturdays in the current booking season.
    Entries where book_type is null are already booked.

    Args:
        rental_url_or_id: Property ID (e.g. "161"), a canonical URL
            (e.g. "https://www.carolinadesigns.com/corolla-vacation-rental/161-ocean-sol/"),
            or a /property-detail-page/{id} URL.
    """
    return await asyncio.to_thread(_client.get_rental_details, rental_url_or_id)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
