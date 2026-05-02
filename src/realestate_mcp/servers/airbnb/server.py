"""MCP server for Airbnb stay search.

Airbnb does not publish a public REST API. This server scrapes their
server-rendered search page and parses the embedded Apollo/Niobe JSON
state. Use of this server is at your own risk under Airbnb's Terms of
Service.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import _client

mcp = FastMCP("airbnb")

_PROXY = os.environ.get("AIRBNB_PROXY_URL", "")


@mcp.tool()
async def search_stays(
    city: str,
    check_in: str = "",
    check_in_dates: list[str] | None = None,
    check_out: str = "",
    nights: int = 0,
    adults: int = 2,
    min_bedrooms: int = 0,
    min_bathrooms: int = 0,
    price_min: int = 0,
    price_max: int = 0,
    max_results: int = 50,
) -> dict[str, Any]:
    """Search Airbnb stays in a city.

    Returns a dict with `search_area`, `total_returned`, and `listings`.
    Each listing has: listing_id, url, name, property_type, bedrooms, beds,
    bathrooms, latitude, longitude, rating, review_count, check_in,
    check_out, nights, total_price, price_currency, price_display, image_url.

    Provide `check_in` for a single date OR `check_in_dates` for a list of
    candidate dates (each searched in parallel; per-listing the cheapest
    matching date is kept). When using either, also provide `check_out` OR
    `nights`. With `check_in_dates`, results are sorted by total_price asc.

    Args:
        city: Free-text city/area (e.g. "Asheville, NC", "Paris, France").
              Geocoded via OpenStreetMap Nominatim.
        check_in: ISO date YYYY-MM-DD. Use this for a single check-in.
        check_in_dates: List of ISO dates to try (e.g. ["2026-07-04",
                        "2026-07-05"] for "Sat or Sun"). Mutually
                        exclusive with `check_in`.
        check_out: ISO date. Provide this OR `nights`. Ignored when
                   `check_in_dates` is used (use `nights` there).
        nights: Stay duration. Provide this OR `check_out`. Required
                when `check_in_dates` is used.
        adults: Number of adults (default 2).
        min_bedrooms: Minimum bedroom count; 0 = any.
        min_bathrooms: Minimum bathroom count; 0 = any.
        price_min: Minimum nightly price in USD; 0 = unset.
        price_max: Maximum nightly price in USD; 0 = unset.
        max_results: Cap on returned listings (default 50).
    """
    if check_in_dates:
        if check_in:
            raise ValueError("Provide either check_in or check_in_dates, not both")
        if not nights:
            raise ValueError("nights is required when using check_in_dates")
        per_date = await asyncio.gather(
            *[
                asyncio.to_thread(
                    _client.search_stays,
                    city=city,
                    check_in=d,
                    check_out=None,
                    nights=nights,
                    adults=adults,
                    min_bedrooms=min_bedrooms,
                    min_bathrooms=min_bathrooms,
                    price_min=price_min,
                    price_max=price_max,
                    max_results=max_results,
                    proxy_url=_PROXY,
                )
                for d in check_in_dates
            ]
        )
        return _client.merge_search_results(per_date, max_results)

    if not check_in:
        raise ValueError("Provide either check_in or check_in_dates")
    return await asyncio.to_thread(
        _client.search_stays,
        city=city,
        check_in=check_in,
        check_out=check_out or None,
        nights=nights or None,
        adults=adults,
        min_bedrooms=min_bedrooms,
        min_bathrooms=min_bathrooms,
        price_min=price_min,
        price_max=price_max,
        max_results=max_results,
        proxy_url=_PROXY,
    )


@mcp.tool()
async def get_listing_details(
    room_url_or_id: str,
    check_in: str = "",
    check_out: str = "",
    adults: int = 2,
) -> dict[str, Any]:
    """Fetch full details for a single Airbnb listing.

    Returns a dict with: listing_id, url, title, description, max_guests,
    sleeping_arrangements, location_subtitle, latitude, longitude,
    host_name, host_is_superhost, host_is_verified, host_about,
    host_review_count, overall_rating, review_count, rating_breakdown,
    is_guest_favorite, amenities, unavailable_amenities, highlights,
    house_rules, cancellation_policy, image_urls.

    Pricing is NOT included — Airbnb loads PDP prices via a separate async
    call. Use `search_stays` for total prices on specific dates.

    Args:
        room_url_or_id: airbnb.com/rooms/<id> URL or bare numeric ID.
        check_in, check_out: Optional ISO dates. They influence which
            listing layout Airbnb returns; do not affect pricing here.
        adults: Number of adults (default 2).
    """
    return await asyncio.to_thread(
        _client.get_listing_details,
        room_url_or_id,
        check_in=check_in or None,
        check_out=check_out or None,
        adults=adults,
        proxy_url=_PROXY,
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
