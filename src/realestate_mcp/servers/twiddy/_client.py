"""Minimal Twiddy & Company vacation rental search client.

Strategy: Twiddy's React SPA calls a first-party JSON REST API at
https://www.twiddy.com/web-api/PropertyApi/. The API base URL and
endpoint paths are embedded in the compiled JS bundle. No auth token
is required — cookies from a Chrome-impersonating request are sufficient.

Two endpoints are used:
  POST /web-api/PropertyApi/Search        — paginated-all town listings
  GET  /web-api/PropertyApi/Info/{id}     — property details (description, beds, baths, location)
  GET  /web-api/PropertyApi/Amenities?propertyId={id}  — amenity list + sleeps count
  GET  /web-api/PropertyApi/GetAvailabilityCalendar/{id}  — weekly availability + rates

Image URLs are constructed as:
  https://www.twiddy.com/property-images/{image_token}

where `image_token` is the raw string from the `images` array in the search
result (format: "{numericId}?v={hash}").

Per-week pricing is available from GetAvailabilityCalendar and is surfaced
in get_rental_details. Arbitrary-date quotes require the booking flow and
are not available here.
"""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from typing import Any

from curl_cffi import requests

_API_BASE = "https://www.twiddy.com"
_SEARCH_URL = f"{_API_BASE}/web-api/PropertyApi/Search"
_INFO_URL = f"{_API_BASE}/web-api/PropertyApi/Info"
_AMENITIES_URL = f"{_API_BASE}/web-api/PropertyApi/Amenities"
_CALENDAR_URL = f"{_API_BASE}/web-api/PropertyApi/GetAvailabilityCalendar"
_IMAGE_BASE = f"{_API_BASE}/property-images"

TWIDDY_PROXY = os.environ.get("TWIDDY_PROXY_URL", "")

# Town display names used in the API, keyed by normalised slug.
TOWN_NAMES: dict[str, str] = {
    "corolla": "Corolla",
    "duck": "Duck",
    "southern-shores": "Southern Shores",
    "kill-devil-hills": "Kill Devil Hills",
    "nags-head": "Nags Head",
    "4x4": "4x4",
}

_INT_RE = re.compile(r"(\d+)")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_PROPERTY_ID_RE = re.compile(r'(?:propertyId|unitId)["\s]*[=:]["\\s]*(\d+)', re.IGNORECASE)


@dataclass
class RentalListing:
    listing_id: int
    url: str
    name: str
    bedrooms: int | None
    bathrooms: str | None
    town: str
    neighborhood: str | None
    distance_to_beach: str | None
    image_url: str | None
    oceanfront: bool
    pet_friendly: bool
    private_pool: bool
    sleeps: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WeeklyRate:
    arrive: str
    depart: str
    weekly_rate: float | None
    is_available: bool
    week_content: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RentalDetails:
    listing_id: int
    url: str
    name: str
    town: str
    neighborhood: str | None
    bedrooms: int | None
    bathrooms_full: int | None
    bathrooms_half: int | None
    sleeps: int | None
    description: str
    amenities: list[str]
    image_urls: list[str]
    weekly_rates: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _strip_html(text: str | None) -> str:
    if not text:
        return ""
    return _HTML_TAG_RE.sub(" ", text).replace("\xa0", " ").replace("&nbsp;", " ").strip()


def _parse_baths_summary(summary: str | None) -> tuple[int | None, int | None]:
    """Parse '9 Full 1 Half' -> (9, 1) or '3 Full' -> (3, 0)."""
    if not summary:
        return None, None
    full_match = re.search(r"(\d+)\s+Full", summary, re.IGNORECASE)
    half_match = re.search(r"(\d+)\s+Half", summary, re.IGNORECASE)
    full = int(full_match.group(1)) if full_match else None
    half = int(half_match.group(1)) if half_match else 0
    return full, half


def _parse_bedrooms(bedrooms_str: str | None) -> int | None:
    """Parse '10 beds' -> 10."""
    if not bedrooms_str:
        return None
    m = _INT_RE.search(bedrooms_str)
    return int(m.group(1)) if m else None


def _build_image_url(token: str | None) -> str | None:
    """Build a full image URL from the raw token in search results."""
    if not token:
        return None
    return f"{_IMAGE_BASE}/{token}"


def _extract_neighborhood(property_url: str) -> str | None:
    """Extract neighborhood from URL like /outer-banks/{town}/{neighborhood}/rentals/{slug}/."""
    parts = property_url.strip("/").split("/")
    # Expected: ['outer-banks', town, neighborhood, 'rentals', slug]
    if len(parts) >= 3 and parts[0] == "outer-banks":
        return parts[2].replace("-", " ").title()
    return None


def _coerce_id(rental_url_or_id: str | int) -> int:
    """Extract numeric property ID from a URL, bare string, or int.

    Accepts:
    - A bare int: 5744 (e.g. listing_id from search_rentals output)
    - A plain integer string: "5744"
    - A Twiddy property URL: "https://www.twiddy.com/outer-banks/..."
    - A bare URL path: "/outer-banks/..."

    For URL inputs, fetches the detail page and reads the embedded propertyId.
    """
    if isinstance(rental_url_or_id, int):
        return rental_url_or_id
    stripped = rental_url_or_id.strip()
    if stripped.isdigit():
        return int(stripped)

    if "twiddy.com" in stripped or stripped.startswith("/outer-banks/"):
        if stripped.startswith("/"):
            stripped = f"{_API_BASE}{stripped}"
        r = requests.get(
            stripped,
            impersonate="chrome124",
            headers={"Accept-Language": "en"},
            proxies={"http": TWIDDY_PROXY, "https": TWIDDY_PROXY} if TWIDDY_PROXY else None,
            timeout=30,
        )
        r.raise_for_status()
        m = _PROPERTY_ID_RE.search(r.text)
        if m:
            return int(m.group(1))
        raise ValueError(f"Cannot extract propertyId from page at {stripped!r}")

    raise ValueError(f"Cannot extract listing ID from {rental_url_or_id!r}")


def _headers() -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": _API_BASE,
        "Referer": f"{_API_BASE}/",
    }


def _proxies() -> dict[str, str] | None:
    return {"http": TWIDDY_PROXY, "https": TWIDDY_PROXY} if TWIDDY_PROXY else None


def _parse_search_results(payload: dict, town_slug: str) -> list[RentalListing]:
    """Parse the /web-api/PropertyApi/Search response."""
    results = payload.get("results")
    if results is None:
        raise RuntimeError("Unexpected Twiddy response shape: missing 'results' key")

    listings: list[RentalListing] = []
    for raw in results:
        prop_id = raw.get("propertyId")
        if not prop_id:
            continue

        prop_url = raw.get("propertyUrl") or ""
        full_url = f"{_API_BASE}{prop_url}" if prop_url.startswith("/") else prop_url

        bedrooms = _parse_bedrooms(raw.get("bedrooms"))

        neighborhood = _extract_neighborhood(prop_url)

        distance = raw.get("distanceToBeach") or ""
        oceanfront = distance.lower() == "oceanfront"

        images = raw.get("images") or []
        image_url = _build_image_url(images[0]) if images else None

        # Sleeps is encoded in amenityItems as '(Sleeps N)'
        sleeps: int | None = None
        for ai in raw.get("amenityItems") or []:
            desc = ai.get("description") or ""
            m = re.search(r"\(Sleeps\s+(\d+)\)", desc, re.IGNORECASE)
            if m:
                sleeps = int(m.group(1))
                break

        # Pet/pool status not present in search payload — defaults to False;
        # the Amenities endpoint provides this for the details call.
        listings.append(
            RentalListing(
                listing_id=prop_id,
                url=full_url,
                name=raw.get("propertyName") or "",
                bedrooms=bedrooms,
                bathrooms=None,
                town=raw.get("town") or town_slug,
                neighborhood=neighborhood,
                distance_to_beach=distance or None,
                image_url=image_url,
                oceanfront=oceanfront,
                pet_friendly=False,
                private_pool=False,
                sleeps=sleeps,
            )
        )
    return listings


def _parse_rental_details(
    info: dict,
    amenities_payload: dict,
    calendar_payload: dict,
    listing_id: int,
) -> RentalDetails:
    """Combine Info + Amenities + Calendar into a RentalDetails."""
    prop_id = info.get("propertyID")
    if prop_id is None:
        raise RuntimeError("Unexpected Twiddy response shape: missing 'propertyID' key in Info")

    full_url_path = info.get("fullUrl") or ""
    full_url = f"{_API_BASE}{full_url_path}" if full_url_path.startswith("/") else full_url_path

    town_raw = info.get("city") or ""
    town_slug = town_raw.lower().replace(" ", "-")

    baths_summary = amenities_payload.get("bathroomsSummary")
    baths_full, baths_half = _parse_baths_summary(baths_summary)

    bedrooms = amenities_payload.get("bedrooms")
    sleeps = amenities_payload.get("sleepsCount")

    # Collect amenity labels from featuredAmenities (surfaced prominently in the UI)
    sm = amenities_payload.get("sectionModel") or {}
    amenities: list[str] = [
        a["displayLabel"]
        for a in (sm.get("featuredAmenities") or [])
        if a.get("displayLabel")
    ]

    # Images from amenities endpoint are not directly available; use exteriorImage
    # from Info as the primary image, supplemented by nothing else at search scope.
    exterior = info.get("exteriorImage")
    image_urls = [exterior] if exterior else []

    # Weekly rates from the availability calendar. The numeric `weeklyRate` field
    # IS the actual price the customer pays — confirmed against the rendered
    # `weekContent` HTML, which uses `<s>$old</s> <strong class="text-orange">$now</strong>`.
    # The numeric matches the orange/<strong> "now" price; the <s> strikethrough is
    # the superseded list price (sometimes higher, sometimes lower than current).
    weekly_rates: list[dict[str, Any]] = []
    for year_obj in calendar_payload.get("availabilityYears") or []:
        for month in year_obj.get("months") or []:
            for week in month.get("weeks") or []:
                arrive = (week.get("arrive") or "")[:10]
                depart = (week.get("depart") or "")[:10]
                raw_rate = week.get("weeklyRate")
                weekly_rate = float(raw_rate) if raw_rate is not None else None
                weekly_rates.append(
                    WeeklyRate(
                        arrive=arrive,
                        depart=depart,
                        weekly_rate=weekly_rate,
                        is_available=bool(week.get("isAvailable")),
                        week_content=_strip_html(week.get("weekContent")),
                    ).to_dict()
                )

    neighborhood = info.get("neighborhood")

    return RentalDetails(
        listing_id=listing_id,
        url=full_url,
        name=info.get("name") or "",
        town=town_slug,
        neighborhood=neighborhood,
        bedrooms=bedrooms,
        bathrooms_full=baths_full,
        bathrooms_half=baths_half,
        sleeps=sleeps,
        description=info.get("description") or "",
        amenities=amenities,
        image_urls=image_urls,
        weekly_rates=weekly_rates,
    )


def search_rentals(
    town: str,
    min_bedrooms: int = 0,
    max_results: int = 50,
) -> dict[str, Any]:
    """Fetch active rentals for a given OBX town, filtered by min_bedrooms.

    Returns {"search_area", "total_returned", "listings"}.

    The API returns all results in one call (no pagination). max_results
    caps the returned list after bedroom filtering.

    Per-week pricing is NOT present in search results. Use get_rental_details
    to obtain weekly availability rates for a specific property.

    pet_friendly and private_pool are not populated in search results because
    the Search endpoint does not surface amenity data. Use get_rental_details.
    """
    town_slug = town.strip().lower()
    town_display = TOWN_NAMES.get(town_slug)
    if town_display is None:
        valid = ", ".join(TOWN_NAMES)
        raise ValueError(f"Unknown town {town!r}. Valid towns: {valid}")

    r = requests.post(
        _SEARCH_URL,
        impersonate="chrome124",
        headers=_headers(),
        proxies=_proxies(),
        json={"townCriteria": [{"criteriaName": town_display}]},
        timeout=30,
    )
    r.raise_for_status()
    payload = r.json()

    all_listings = _parse_search_results(payload, town_slug)

    filtered = [li for li in all_listings if (li.bedrooms or 0) >= min_bedrooms]
    capped = filtered[:max_results]

    return {
        "search_area": f"{town_display}, NC (Outer Banks)",
        "total_returned": len(capped),
        "listings": [li.to_dict() for li in capped],
    }


def get_rental_details(rental_url_or_id: str | int) -> dict[str, Any]:
    """Fetch full details for a single Twiddy property.

    Accepts a numeric property ID (e.g. "5744") or a canonical Twiddy URL
    (e.g. "https://www.twiddy.com/outer-banks/corolla/pine-island/rentals/station-one/").

    Returns {listing_id, url, name, town, neighborhood, bedrooms,
    bathrooms_full, bathrooms_half, sleeps, description, amenities,
    image_urls, weekly_rates}.

    weekly_rates is a list of {arrive, depart, weekly_rate, is_available,
    week_content} for each week in the current and next rental season.
    `weekly_rate` is the price the customer actually pays. `week_content` is
    the rendered display string, which can include a strikethrough of a
    superseded price (e.g. "Weekly rate $11,250 $15,000" — the strikethrough
    `$11,250` is an old/superseded price; `$15,000` matches `weekly_rate` and
    is what the customer pays).
    """
    prop_id = _coerce_id(rental_url_or_id)
    prox = _proxies()

    r_info = requests.get(
        f"{_INFO_URL}/{prop_id}",
        impersonate="chrome124",
        headers=_headers(),
        proxies=prox,
        timeout=30,
    )
    r_info.raise_for_status()
    info = r_info.json()

    r_amen = requests.get(
        _AMENITIES_URL,
        impersonate="chrome124",
        headers=_headers(),
        proxies=prox,
        params={"propertyId": prop_id},
        timeout=30,
    )
    r_amen.raise_for_status()
    amenities_payload = r_amen.json()

    r_cal = requests.get(
        f"{_CALENDAR_URL}/{prop_id}",
        impersonate="chrome124",
        headers=_headers(),
        proxies=prox,
        timeout=30,
    )
    r_cal.raise_for_status()
    calendar_payload = r_cal.json()

    return _parse_rental_details(info, amenities_payload, calendar_payload, prop_id).to_dict()
