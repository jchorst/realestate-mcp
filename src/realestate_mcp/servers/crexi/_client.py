"""Minimal Crexi commercial real estate search client.

Strategy: Crexi exposes a public-ish JSON REST API at https://api.crexi.com.
No auth token is required; Chrome-impersonating requests work fine.

Endpoints used:
  POST https://api.crexi.com/assets/search
      Body: { query, includeUnpriced, take }
      Returns: { data: [...], totalCount }
      Each item has: id, name, description, thumbnailUrl, urlSlug, locations,
      askingPrice, squareFootage, types, status, brokerageName, ...

  GET  https://api.crexi.com/assets/{id}
      Returns the full listing detail: marketingDescription, details (dict),
      summaryDetails (list), locations, types, status, urlSlug, askingPrice, ...

  GET  https://api.crexi.com/assets/{id}/brokers
      Returns a list of broker objects with firstName, lastName, brokerage, ...

  GET  https://api.crexi.com/assets/{id}/gallery
      Returns a list of image objects with imageUrl.

The API always returns a maximum of 50 results per search request regardless
of the `take` value. Server-side property-type and price filters are accepted
but appear to have no effect as of 2026-05; price and type filtering is done
client-side. The `skip` parameter is also ignored — pagination is not supported
by this endpoint.

Property URL format: https://www.crexi.com/properties/{urlSlug}/{id}
"""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from typing import Any

from curl_cffi import requests
from curl_cffi.requests import RequestsError

CREXI_API_BASE = "https://api.crexi.com"
CREXI_WEB_BASE = "https://www.crexi.com"

CREXI_PROXY = os.environ.get("CREXI_PROXY_URL", "")

_NUMERIC_ID_RE = re.compile(r"/(\d+)$")


@dataclass
class PropertySummary:
    listing_id: str
    url: str
    name: str
    address: str
    city: str
    state: str
    zip: str
    price: float | None
    property_type: str
    building_sqft: int | None
    image_url: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PropertyDetail:
    listing_id: str
    url: str
    name: str
    address: str
    city: str
    state: str
    zip: str
    price: float | None
    property_type: str
    description: str
    building_sqft: int | None
    lot_acres: float | None
    year_built: str | None
    image_urls: list[str]
    broker_names: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _coerce_id(listing_id_or_url: str | int) -> str:
    """Extract a numeric asset ID from a URL, bare numeric string, or integer.

    Raises ValueError when no numeric ID can be found. Hex property-record IDs
    from `/properties/search` are intentionally rejected here — `/assets/{id}`
    only resolves numeric asset IDs, so accepting hex would silently 404.
    """
    if isinstance(listing_id_or_url, int):
        return str(listing_id_or_url)
    s = str(listing_id_or_url).strip()
    m = _NUMERIC_ID_RE.search(s)
    if m:
        return m.group(1)
    if s.isdigit():
        return s
    raise ValueError(f"Cannot extract listing ID from {listing_id_or_url!r}")


def _extract_lot_acres(details: dict[str, str]) -> float | None:
    """Pull lot acreage from the details dict, which may use several different keys."""
    for key in ("Lot Size (acres)", "Lot Size (Acres)", "Land Area (acres)"):
        val = details.get(key)
        if val:
            try:
                return float(val.replace(",", ""))
            except ValueError:
                return None
    return None


def _extract_sqft_from_summary(summary_details: list[dict]) -> int | None:
    """Walk summaryDetails for the SquareFootage key."""
    for entry in summary_details:
        if entry.get("key") == "SquareFootage":
            try:
                return int(entry["value"])
            except (KeyError, ValueError, TypeError):
                return None
    return None


def _extract_year_built(details: dict[str, str]) -> str | None:
    return details.get("Year Built") or details.get("Year Renovated") or None


def _parse_location(locations: list[dict]) -> tuple[str, str, str, str]:
    """Return (address, city, state_code, zip) from the locations list."""
    if not locations:
        return "", "", "", ""
    loc = locations[0]
    state_obj = loc.get("state") or {}
    state_code = (
        state_obj.get("code") if isinstance(state_obj, dict) else str(state_obj or "")
    )
    return (
        loc.get("address") or "",
        loc.get("city") or "",
        state_code or "",
        loc.get("zip") or "",
    )


def _parse_search_result(raw: dict) -> PropertySummary:
    """Parse one item from the assets/search data array."""
    try:
        listing_id = str(raw["id"])
    except KeyError as e:
        raise RuntimeError(f"Unexpected Crexi response shape: missing {e}") from e

    url_slug = raw.get("urlSlug") or ""
    url = f"{CREXI_WEB_BASE}/properties/{url_slug}/{listing_id}" if url_slug else ""
    address, city, state, zip_ = _parse_location(raw.get("locations") or [])

    types = raw.get("types") or []
    property_type = ", ".join(types) if types else ""

    return PropertySummary(
        listing_id=listing_id,
        url=url,
        name=raw.get("name") or "",
        address=address,
        city=city,
        state=state,
        zip=zip_,
        price=raw.get("askingPrice"),
        property_type=property_type,
        building_sqft=raw.get("squareFootage"),
        image_url=raw.get("thumbnailUrl"),
    )


def _parse_search_response(payload: dict, max_results: int) -> list[PropertySummary]:
    """Parse the full assets/search POST response."""
    try:
        items = payload["data"]
    except KeyError as e:
        raise RuntimeError(f"Unexpected Crexi response shape: missing {e}") from e
    if not isinstance(items, list):
        raise RuntimeError("Unexpected Crexi response shape: 'data' is not a list")

    results: list[PropertySummary] = []
    for raw in items:
        results.append(_parse_search_result(raw))
        if len(results) >= max_results:
            break
    return results


def _parse_asset_detail(payload: dict, listing_id: str) -> PropertyDetail:
    """Parse the GET /assets/{id} response into a PropertyDetail dataclass."""
    if not isinstance(payload, dict):
        raise RuntimeError("Unexpected Crexi response shape: asset detail is not a dict")

    url_slug = payload.get("urlSlug") or ""
    locations = payload.get("locations") or []
    types = payload.get("types") or []
    asking_price = payload.get("askingPrice")
    name = payload.get("name") or ""

    url = f"{CREXI_WEB_BASE}/properties/{url_slug}/{listing_id}" if url_slug else ""
    address, city, state, zip_ = _parse_location(locations)
    property_type = ", ".join(types) if types else ""

    details: dict[str, str] = payload.get("details") or {}
    summary_details: list[dict] = payload.get("summaryDetails") or []

    raw_desc = payload.get("marketingDescription") or payload.get("description") or ""
    description = re.sub(r"<[^>]+>", " ", raw_desc).replace("\xa0", " ").strip()

    sqft = _extract_sqft_from_summary(summary_details)
    if sqft is None and details.get("Square Footage"):
        try:
            sqft = int(details["Square Footage"].replace(",", ""))
        except ValueError:
            sqft = None

    return PropertyDetail(
        listing_id=listing_id,
        url=url,
        name=name,
        address=address,
        city=city,
        state=state,
        zip=zip_,
        price=asking_price,
        property_type=property_type,
        description=description,
        building_sqft=sqft,
        lot_acres=_extract_lot_acres(details),
        year_built=_extract_year_built(details),
        image_urls=[],
        broker_names=[],
    )


def _fetch_gallery_images(asset_id: str, proxy_url: str = "") -> list[str]:
    """Fetch the asset gallery and return a list of full-resolution image URLs."""
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
    r = requests.get(
        f"{CREXI_API_BASE}/assets/{asset_id}/gallery",
        impersonate="chrome124",
        headers={"Accept-Language": "en", "Accept": "application/json"},
        proxies=proxies,
        timeout=20,
    )
    if r.status_code == 404:
        return []
    r.raise_for_status()
    items = r.json()
    if not isinstance(items, list):
        return []
    return [item["imageUrl"] for item in items if item.get("imageUrl")]


def _fetch_broker_names(asset_id: str, proxy_url: str = "") -> list[str]:
    """Fetch all brokers' full names from the brokers endpoint."""
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
    r = requests.get(
        f"{CREXI_API_BASE}/assets/{asset_id}/brokers",
        impersonate="chrome124",
        headers={"Accept-Language": "en", "Accept": "application/json"},
        proxies=proxies,
        timeout=20,
    )
    if r.status_code in (401, 403, 404):
        return []
    r.raise_for_status()
    brokers = r.json()
    if not isinstance(brokers, list):
        return []
    names: list[str] = []
    for b in brokers:
        first_name = b.get("firstName") or ""
        last_name = b.get("lastName") or ""
        full_name = f"{first_name} {last_name}".strip()
        if full_name:
            names.append(full_name)
    return names


def search_properties(
    query: str,
    property_type: str = "",
    min_price: int = 0,
    max_price: int = 0,
    max_results: int = 50,
    proxy_url: str = "",
) -> dict[str, Any]:
    """Search Crexi for commercial real estate listings.

    Returns {"search_query", "total_returned", "properties"}.
    Each property dict has: listing_id, url, name, address, city, state, zip,
    price, property_type, building_sqft, image_url.

    Note: Crexi's API returns at most 50 results per request regardless of
    max_results. Client-side price and property_type filtering is applied
    after fetch when those params are provided.
    """
    if not query:
        raise ValueError("query is required")

    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
    r = requests.post(
        f"{CREXI_API_BASE}/assets/search",
        json={"query": query, "includeUnpriced": True, "take": 50},
        impersonate="chrome124",
        headers={
            "Accept-Language": "en",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        proxies=proxies,
        timeout=30,
    )
    r.raise_for_status()
    payload = r.json()
    # Parse all 50 first, then filter, then cap — server-side filters aren't honored.
    properties = _parse_search_response(payload, max_results=50)

    if property_type:
        pt_lower = property_type.lower()
        properties = [p for p in properties if pt_lower in p.property_type.lower()]

    if min_price:
        properties = [p for p in properties if p.price is not None and p.price >= min_price]

    if max_price:
        properties = [p for p in properties if p.price is not None and p.price <= max_price]

    properties = properties[:max_results]
    return {
        "search_query": query,
        "total_returned": len(properties),
        "properties": [p.to_dict() for p in properties],
    }


def get_property_details(
    listing_id_or_url: str | int,
    proxy_url: str = "",
) -> dict[str, Any]:
    """Fetch full detail for a single Crexi listing.

    Accepts a bare numeric asset ID, a full crexi.com/properties/... URL,
    or a hex string property-record ID (from the property-records API).

    Returns a dict with: listing_id, url, name, address, city, state, zip,
    price, property_type, description, building_sqft, lot_acres, year_built,
    image_urls, broker_names.

    broker_names is the full list of co-listing brokers (CRE listings often
    have 2-3). Phone numbers aren't surfaced by the public API.
    Gallery images and broker names are fetched via two additional HTTP calls;
    network failures in either are tolerated so that a missing gallery or
    auth-walled brokers endpoint doesn't break the detail response.
    """
    asset_id = _coerce_id(listing_id_or_url)

    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
    r = requests.get(
        f"{CREXI_API_BASE}/assets/{asset_id}",
        impersonate="chrome124",
        headers={"Accept-Language": "en", "Accept": "application/json"},
        proxies=proxies,
        timeout=30,
    )
    r.raise_for_status()
    payload = r.json()

    detail = _parse_asset_detail(payload, asset_id)

    try:
        detail.image_urls = _fetch_gallery_images(asset_id, proxy_url=proxy_url)
    except RequestsError:
        detail.image_urls = []

    try:
        detail.broker_names = _fetch_broker_names(asset_id, proxy_url=proxy_url)
    except RequestsError:
        detail.broker_names = []

    return detail.to_dict()
