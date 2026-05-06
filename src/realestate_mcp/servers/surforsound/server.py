"""MCP server for Surf or Sound Realty vacation rental search.

Surf or Sound manages 300+ vacation rentals on Hatteras Island, NC, covering
the villages of Rodanthe, Waves, Salvo, Avon, Buxton, Frisco, and Hatteras
— the south-OBX area not covered by Carolina Designs or Twiddy.

This server scrapes their public search and property detail pages using
BeautifulSoup4 on server-rendered HTML.
"""

from __future__ import annotations

import asyncio
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import _client

mcp = FastMCP("surforsound")


@mcp.tool()
async def search_rentals(
    town: str,
    min_bedrooms: int = 0,
    max_results: int = 50,
    check_in: str = "",
) -> dict[str, Any]:
    """Search Surf or Sound vacation rentals by Hatteras Island village.

    Returns a dict with `search_area`, `total_returned`, and `listings`.
    Each listing has: listing_id, url, name, bedrooms, bathrooms_full,
    bathrooms_half, town, location, weekly_rate (USD float for the
    requested check_in date or the site default), check_in.

    Args:
        town: One of: rodanthe, waves, salvo, avon, buxton, frisco, hatteras.
        min_bedrooms: Minimum bedroom count; 0 = any.
        max_results: Cap on returned listings (default 50).
        check_in: Optional arrival date YYYY-MM-DD (Saturday). When provided,
            weekly_rate reflects that specific week's price. When omitted, the
            site defaults to the upcoming Saturday arrival.
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
    """Fetch full details for a single Surf or Sound rental property.

    Returns a dict with: listing_id, url, name, town, bedrooms,
    bathrooms_full, bathrooms_half, sleeps (always None — not surfaced
    by the site), description, amenities, image_urls, weekly_rate_min,
    weekly_rate_max, weekly_availabilities.

    weekly_rate_min / weekly_rate_max are parsed from the "Weekly: $X - $Y"
    range displayed on the page.

    weekly_availabilities is a list of {start_date, rate, formatted_rate,
    reference_rate, is_on_special} for all available weeks embedded as JSON
    in the page's JavaScript.

    Args:
        rental_url_or_id: Numeric property ID (e.g. "553") or a full
            Surf or Sound URL (e.g.
            "https://www.surforsound.com/hatteras-vacation-rental/property/553").
    """
    return await asyncio.to_thread(_client.get_rental_details, rental_url_or_id)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
