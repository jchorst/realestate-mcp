"""Minimal Carolina Designs Realty search client.

Strategy: Carolina Designs exposes an authenticated JSON REST API at
https://siteservice.carolinadesigns.com/websiteservice.svc/10000/32
The credentials (Authorization header + API path) are embedded in their
public main.js bundle and are scoped to read-only website data — no
account or booking operations are possible.

Two endpoints are used:
  GET /website/searchresults/{town_id}/d  — paginated-all town listings
  GET /website/properties/d/{prop_id}     — single property detail

The Angular frontend loads listings dynamically via XHR; the town index
HTML pages render only a spinner. Direct use of this API is therefore the
only viable path — HTML scraping of the town pages would yield zero results.

Per-week pricing IS available in Weeks1CurrAvail / Weeks2CurrAvail on the
detail endpoint (list of {ArrivalDate, Rate, Orate, CostPerNight} per
available Saturday). Arbitrary-date quotes are not available without a
booking flow, but the weekly availability data is surfaced in get_rental_details.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from curl_cffi import requests

_API_BASE = "https://siteservice.carolinadesigns.com/websiteservice.svc/10000/32"
_AUTH = "Basic NzUyOTIxRUYtRjQzQS00Q0YyLUJCMEUtOUIwM0JGN0E5NDdE"
_SITE_BASE = "https://www.carolinadesigns.com"

_HEADERS = {
    "Authorization": _AUTH,
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Origin": _SITE_BASE,
    "Referer": _SITE_BASE + "/",
}

# Town slug → numeric searchType id, sourced from main.js bundle constant C.
TOWN_IDS: dict[str, str] = {
    "corolla": "32",
    "duck": "33",
    "southern-shores": "34",
    "kitty-hawk": "35",
    "kill-devil-hills": "36",
    "nags-head": "37",
}

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_PRICE_RE = re.compile(r"\$([\d,]+(?:\.\d+)?)")
_INT_RE = re.compile(r"(\d+)")


@dataclass
class RentalListing:
    listing_id: str
    url: str
    name: str
    bedrooms: int | None
    bathrooms_full: int | None
    bathrooms_half: int | None
    town: str
    location: str | None
    subdivision: str | None
    image_url: str | None
    pet_friendly: bool
    private_pool: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WeeklyRate:
    arrival_date: str
    weekly_rate: str | None
    nightly_rate: str | None
    book_type: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RentalDetails:
    listing_id: str
    url: str
    name: str
    town: str
    bedrooms: int | None
    bathrooms_full: int | None
    bathrooms_half: int | None
    sleeps: int | None
    description: str
    amenities: list[str]
    image_urls: list[str]
    weekly_rates: list[dict[str, Any]]
    min_price: int | None
    max_price: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _strip_html(text: str | None) -> str:
    if not text:
        return ""
    return _HTML_TAG_RE.sub(" ", text).replace("\xa0", " ").replace("&nbsp;", " ").strip()


def _parse_baths(baths_str: str | None) -> tuple[int | None, int | None]:
    """Parse '15/2' → (15, 2) or '3' → (3, 0)."""
    if not baths_str:
        return None, None
    parts = baths_str.split("/")
    m0 = _INT_RE.match(parts[0].strip())
    full = int(m0.group(1)) if m0 else None
    if len(parts) > 1:
        m1 = _INT_RE.match(parts[1].strip())
        half = int(m1.group(1)) if m1 else 0
    else:
        half = 0
    return full, half


def _coerce_id(rental_url_or_id: str) -> str:
    """Extract numeric property ID from a URL or bare string."""
    m = re.search(r"/(\d+)(?:[^\d/]|$)", rental_url_or_id)
    if m:
        return m.group(1)
    if rental_url_or_id.strip().isdigit():
        return rental_url_or_id.strip()
    raise ValueError(f"Cannot extract listing ID from {rental_url_or_id!r}")


def _parse_search_results(payload: dict, town_slug: str) -> list[RentalListing]:
    """Parse the /website/searchresults/{id}/d response."""
    results = payload.get("Results")
    if results is None:
        raise RuntimeError(
            "Unexpected Carolina Designs response shape: missing 'Results' key"
        )

    listings: list[RentalListing] = []
    for raw in results:
        prop_id = (raw.get("Propid") or "").strip()
        if not prop_id:
            continue
        baths_full, baths_half = _parse_baths(raw.get("Baths"))
        prop_url = raw.get("PropURL") or ""
        if prop_url and not prop_url.startswith("http"):
            prop_url = _SITE_BASE + prop_url

        listings.append(
            RentalListing(
                listing_id=prop_id,
                url=prop_url or f"{_SITE_BASE}/property-detail-page/{prop_id}",
                name=raw.get("Propname") or "",
                bedrooms=raw.get("Bedrooms"),
                bathrooms_full=baths_full,
                bathrooms_half=baths_half,
                town=town_slug,
                location=raw.get("DisplayLocation"),
                subdivision=raw.get("DisplaySub"),
                image_url=raw.get("ImageURL"),
                pet_friendly=bool(raw.get("PetFriendly")),
                private_pool=bool(raw.get("PrivatePool")),
            )
        )
    return listings


def _parse_rental_details(payload: dict, listing_id: str) -> RentalDetails:
    """Parse the /website/properties/d/{id} response."""
    prop_id = payload.get("Propid")
    if prop_id is None:
        raise RuntimeError(
            "Unexpected Carolina Designs response shape: missing 'Propid' key"
        )

    baths_info = payload.get("Bathroominfo") or []
    baths_full: int | None = None
    baths_half: int | None = None
    for entry in baths_info:
        entry_lower = (entry or "").lower()
        m = _INT_RE.search(entry_lower)
        if not m:
            continue
        val = int(m.group(1))
        if "full" in entry_lower:
            baths_full = val
        elif "half" in entry_lower:
            baths_half = val

    amenities: list[str] = []
    for section in payload.get("Sidebar") or []:
        for item in (section.get("Items") or []):
            if item:
                amenities.append(item)

    image_urls = [
        p["ImgUrl"]
        for p in (payload.get("PicsLarge") or [])
        if (p or {}).get("ImgUrl")
    ]

    weekly_rates: list[dict[str, Any]] = []
    for week_entry in payload.get("Weeks1CurrAvail") or []:
        rate_str = week_entry.get("Rate") or ""
        weekly_rates.append(
            WeeklyRate(
                arrival_date=week_entry.get("ArrivalDate") or "",
                weekly_rate=rate_str if rate_str not in ("$0.00", "") else None,
                nightly_rate=week_entry.get("CostPerNight"),
                book_type=week_entry.get("BookType") or None,
            ).to_dict()
        )

    canonical = payload.get("CanonicalUrl") or f"{_SITE_BASE}/property-detail-page/{listing_id}"
    area = payload.get("Area") or ""
    town_slug = area.lower().replace(" ", "-")

    beds_raw = payload.get("NumBedrooms")
    bedrooms: int | None = None
    if beds_raw is not None:
        m = _INT_RE.match(str(beds_raw))
        bedrooms = int(m.group(1)) if m else None

    sleeps_raw = payload.get("Sleeps")
    sleeps: int | None = None
    if sleeps_raw is not None:
        m = _INT_RE.match(str(sleeps_raw))
        sleeps = int(m.group(1)) if m else None

    return RentalDetails(
        listing_id=str(prop_id),
        url=canonical,
        name=payload.get("Propname") or "",
        town=town_slug,
        bedrooms=bedrooms,
        bathrooms_full=baths_full,
        bathrooms_half=baths_half,
        sleeps=sleeps,
        description=_strip_html(payload.get("Description")),
        amenities=amenities,
        image_urls=image_urls,
        weekly_rates=weekly_rates,
        min_price=payload.get("MinPrice"),
        max_price=payload.get("MaxPrice"),
    )


def search_rentals(
    town: str,
    min_bedrooms: int = 0,
    max_results: int = 50,
) -> dict[str, Any]:
    """Fetch all active rentals for a given town, filtered by min_bedrooms.

    Returns {"search_area", "total_returned", "listings"}.

    The API returns all results in one call (no pagination needed — the
    largest town, Corolla, has 116 listings as of 2026). max_results
    caps the returned list after bedroom filtering.

    Per-week pricing is NOT present in search results. Use get_rental_details
    to obtain Weeks1CurrAvail weekly rates for a specific property.
    """
    town_slug = town.strip().lower()
    town_id = TOWN_IDS.get(town_slug)
    if town_id is None:
        valid = ", ".join(TOWN_IDS)
        raise ValueError(f"Unknown town {town!r}. Valid towns: {valid}")

    r = requests.get(
        f"{_API_BASE}/website/searchresults/{town_id}/d",
        impersonate="chrome124",
        headers=_HEADERS,
        timeout=30,
    )
    r.raise_for_status()
    payload = r.json()

    all_listings = _parse_search_results(payload, town_slug)

    filtered = [li for li in all_listings if (li.bedrooms or 0) >= min_bedrooms]
    capped = filtered[:max_results]

    area_title = (payload.get("Title") or "").strip() or town.title()
    return {
        "search_area": area_title,
        "total_returned": len(capped),
        "listings": [li.to_dict() for li in capped],
    }


def get_rental_details(rental_url_or_id: str) -> dict[str, Any]:
    """Fetch full detail for a single Carolina Designs property.

    Accepts a property ID (e.g. "161"), a canonical URL
    (e.g. "https://www.carolinadesigns.com/corolla-vacation-rental/161-ocean-sol/"),
    or the /property-detail-page/{id} URL pattern.

    Returns {listing_id, url, name, town, bedrooms, bathrooms_full,
    bathrooms_half, sleeps, description, amenities, image_urls,
    weekly_rates, min_price, max_price}.

    weekly_rates is a list of {arrival_date, weekly_rate, nightly_rate,
    book_type} for the current year's available Saturdays. Entries where
    book_type is empty or Rate is $0.00 are already booked.
    """
    prop_id = _coerce_id(rental_url_or_id)
    r = requests.get(
        f"{_API_BASE}/website/properties/d/{prop_id}",
        impersonate="chrome124",
        headers=_HEADERS,
        timeout=30,
    )
    r.raise_for_status()
    payload = r.json()
    return _parse_rental_details(payload, prop_id).to_dict()
