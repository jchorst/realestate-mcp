"""MCP server for Church Realty property search.

IMPORTANT GEOGRAPHIC LIMITATION: Church Realty (churchrealty.com) exclusively
lists church and religious-use properties in Texas. Coverage is limited to the
Dallas-Fort Worth (DFW) and Houston metro areas. Do not query this server for
properties outside Texas — the inventory does not include them.

Typical use-cases:
- A congregation searching for a church building to buy or lease in DFW/Houston.
- A developer looking for religious-use land or redevelopment properties in TX.

Church Realty does not publish a public REST API. This server scrapes their
server-rendered WordPress site and parses the static HTML. Use of this server
is at your own risk under Church Realty's Terms of Service.

Note on pricing: the /properties/ index page does NOT display prices. Prices
are only available on individual detail pages. Use get_listing_details() after
searching to retrieve prices, building stats, and agent contact info.
"""

from __future__ import annotations

import asyncio
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import _client

mcp = FastMCP("churchrealty")


@mcp.tool()
async def search_listings(
    city: str = "",
    state: str = "",
    listing_type: str = "",
    max_results: int = 50,
) -> dict[str, Any]:
    """Search Church Realty listings (Texas-only: DFW and Houston metros).

    Fetches the full /properties/ index (all ~20-30 active listings on one
    page) and applies optional client-side filters. Prices are NOT available
    from the index — use get_listing_details() on specific listings for price,
    building sqft, lot acreage, and agent contact info. There are no price
    filter parameters here for that reason.

    Returns {"search_area", "total_returned", "listings"}. Each listing has:
    listing_id (URL slug), url, name (street address), address, city, state,
    zip, price (always None from index), listing_type ("For Sale" / "For
    Lease" / "Unknown"), image_url.

    Args:
        city: Case-insensitive substring filter on city (e.g. "Houston").
        state: Case-insensitive substring filter on state (e.g. "TX").
        listing_type: "sale"/"buy" for For Sale, "lease"/"rent" for For Lease.
                      Empty string returns all types.
        max_results: Cap on returned listings (default 50).
    """
    return await asyncio.to_thread(
        _client.search_listings,
        city=city,
        state=state,
        listing_type=listing_type,
        max_results=max_results,
    )


@mcp.tool()
async def get_listing_details(listing_url_or_slug: str) -> dict[str, Any]:
    """Fetch full details for a single Church Realty property.

    Returns {listing_id, url, name, address, city, state, zip, price,
    listing_type, description, building_sqft, lot_acres,
    year_built (always None), image_urls, agent_name, agent_phone}.

    price is None when the listing reads "Please call agent for price".
    description is the brief <h3> headline on the page (e.g., "Great Frisco
    location on Preston near 121 & DNT!"); None if the listing omits it.
    agent_phone may include extensions (e.g., "281-540-2008 ext 2").
    year_built is not surfaced anywhere on the site.

    Args:
        listing_url_or_slug: The URL slug (e.g.,
            "church-property-for-sale-houston-tx-10355-mills-road"),
            a full detail URL (e.g.,
            "https://www.churchrealty.com/property/<slug>/"),
            or a bare integer (converted to string as a slug).
    """
    return await asyncio.to_thread(
        _client.get_listing_details,
        listing_url_or_slug,
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
