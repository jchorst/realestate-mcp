"""Minimal Airbnb search client.

Strategy: hit Airbnb's server-rendered search page and parse the embedded
`<script id="data-deferred-state-0">` JSON. This avoids the brittle
GraphQL persisted-query operationId hash entirely — that hash rotates and
its extraction regex breaks regularly. The HTML embed is the same data
the page renders against, so it's stable as long as Airbnb keeps using
their current Niobe/Apollo client architecture.

City → bounding box uses OpenStreetMap Nominatim (free, no key).
"""

from __future__ import annotations

import base64
import contextlib
import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from threading import Lock
from typing import Any
from urllib.parse import urlencode

from curl_cffi import requests

AIRBNB_BASE = "https://www.airbnb.com"
NOMINATIM_BASE = "https://nominatim.openstreetmap.org"
USER_AGENT_NOMINATIM = "realestate-mcp/0.1 (https://github.com/justinhorst/realestate-mcp)"

_SCRIPT_RE = re.compile(
    r'<script id="data-deferred-state-0"[^>]*>(.*?)</script>', re.DOTALL
)
_INT_RE = re.compile(r"(\d+)")
_FLOAT_RE = re.compile(r"(\d+(?:\.\d+)?)")
_PRICE_RE = re.compile(r"([^\d.,]*)\s*([\d,]+(?:\.\d+)?)")


@dataclass
class ListingDetails:
    listing_id: str
    url: str
    title: str
    description: str
    max_guests: int | None
    sleeping_arrangements: list[str]
    location_subtitle: str | None
    latitude: float | None
    longitude: float | None
    host_name: str | None
    host_is_superhost: bool
    host_is_verified: bool
    host_about: str | None
    host_review_count: int | None
    overall_rating: float | None
    review_count: int | None
    rating_breakdown: dict[str, str]
    is_guest_favorite: bool
    amenities: list[str]
    unavailable_amenities: list[str]
    highlights: list[dict[str, str | None]]
    house_rules: list[str]
    cancellation_policy: str | None
    image_urls: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Listing:
    listing_id: str
    url: str
    name: str
    property_type: str
    bedrooms: int | None
    beds: int | None
    bathrooms: float | None
    latitude: float | None
    longitude: float | None
    rating: float | None
    review_count: int | None
    check_in: str
    check_out: str
    nights: int
    total_price: float | None
    price_currency: str | None
    price_display: str | None
    image_url: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BoundingBox:
    sw_lat: float
    sw_lng: float
    ne_lat: float
    ne_lng: float
    display_name: str


_geocode_cache: dict[str, BoundingBox] = {}
_geocode_lock = Lock()
_last_nominatim_call = 0.0


def geocode_city(city: str) -> BoundingBox:
    """Resolve a free-text city/area string to a bounding box via Nominatim.

    Cached in-process. Respects Nominatim's 1 req/sec policy.
    """
    key = city.strip().lower()
    with _geocode_lock:
        if key in _geocode_cache:
            return _geocode_cache[key]

        global _last_nominatim_call
        elapsed = time.monotonic() - _last_nominatim_call
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)

        params = {"q": city, "format": "json", "limit": 1}
        r = requests.get(
            f"{NOMINATIM_BASE}/search",
            params=params,
            headers={"User-Agent": USER_AGENT_NOMINATIM, "Accept-Language": "en"},
            timeout=15,
        )
        _last_nominatim_call = time.monotonic()
        r.raise_for_status()
        results = r.json()
        if not results:
            raise ValueError(f"No geocoding result for {city!r}")
        first = results[0]
        # Nominatim's boundingbox is [minlat, maxlat, minlon, maxlon] as strings.
        minlat, maxlat, minlon, maxlon = (float(v) for v in first["boundingbox"])
        bbox = BoundingBox(
            sw_lat=minlat,
            sw_lng=minlon,
            ne_lat=maxlat,
            ne_lng=maxlon,
            display_name=first.get("display_name", city),
        )
        _geocode_cache[key] = bbox
        return bbox


def _coerce_int(text: str | None) -> int | None:
    if not text:
        return None
    if "studio" in text.lower():
        return 0
    m = _INT_RE.search(text)
    return int(m.group(1)) if m else None


def _coerce_float(text: str | None) -> float | None:
    if not text:
        return None
    if "half" in text.lower():
        return 0.5
    m = _FLOAT_RE.search(text)
    return float(m.group(1)) if m else None


def _decode_listing_id(encoded: str | None) -> str | None:
    if not encoded:
        return None
    try:
        decoded = base64.b64decode(encoded).decode("utf-8")
    except Exception:
        return None
    if ":" in decoded:
        return decoded.split(":", 1)[1]
    return decoded


def _parse_price(price_text: str | None) -> tuple[float | None, str | None]:
    """Parse '$1,450' or '€1.450,00' into (amount, currency_symbol)."""
    if not price_text:
        return None, None
    m = _PRICE_RE.search(price_text)
    if not m:
        return None, None
    symbol, amount_str = m.group(1).strip(), m.group(2)
    try:
        amount = float(amount_str.replace(",", ""))
    except ValueError:
        return None, symbol or None
    return amount, symbol or None


def _structured_field(
    structured_content: dict, keyword: str, *, exclude: str | None = None
) -> str | None:
    """Find the body of the first primaryLine message containing `keyword`.

    Optionally skip bodies that also contain `exclude` (e.g. searching for
    "bed" should skip "3 bedrooms").
    """
    for msg in (structured_content or {}).get("primaryLine") or []:
        body = msg.get("body") or ""
        body_lower = body.lower()
        if keyword not in body_lower:
            continue
        if exclude and exclude in body_lower:
            continue
        return body
    return None


def _parse_search_results(
    payload: dict, check_in: str, check_out: str, nights: int
) -> tuple[list[Listing], list[str]]:
    """Return (listings, page_cursors)."""
    try:
        results_node = payload["niobeClientData"][0][1]["data"]["presentation"][
            "staysSearch"
        ]["results"]
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"Unexpected Airbnb response shape: {e}") from e

    raw_listings = results_node.get("searchResults") or []
    cursors = (results_node.get("paginationInfo") or {}).get("pageCursors") or []

    listings: list[Listing] = []
    for raw in raw_listings:
        if raw.get("__typename") not in (None, "StaySearchResult", "DemandStaysSearchResult"):
            # Skip ad/upsell cards
            pass
        dsl = raw.get("demandStayListing") or {}
        listing_id = _decode_listing_id(dsl.get("id"))
        if not listing_id:
            continue

        sc = raw.get("structuredContent") or {}
        bedrooms = _coerce_int(_structured_field(sc, "bedroom"))
        beds = _coerce_int(_structured_field(sc, "bed", exclude="bedroom"))
        bathrooms = _coerce_float(_structured_field(sc, "bath"))

        sdp = raw.get("structuredDisplayPrice") or {}
        primary = sdp.get("primaryLine") or {}
        price_display = primary.get("discountedPrice") or primary.get("price")
        amount, currency = _parse_price(price_display)

        coord = (dsl.get("location") or {}).get("coordinate") or {}
        rating, review_count = None, None
        rating_text = raw.get("avgRatingLocalized")
        if rating_text:
            rating = _coerce_float(rating_text)
            rc_match = re.search(r"\((\d[\d,]*)\)", rating_text)
            if rc_match:
                review_count = int(rc_match.group(1).replace(",", ""))

        pictures = raw.get("contextualPictures") or []
        image_url = pictures[0].get("picture") if pictures else None

        listings.append(
            Listing(
                listing_id=listing_id,
                url=f"{AIRBNB_BASE}/rooms/{listing_id}",
                name=raw.get("subtitle") or raw.get("nameLocalized") or "",
                property_type=raw.get("title") or "",
                bedrooms=bedrooms,
                beds=beds,
                bathrooms=bathrooms,
                latitude=coord.get("latitude"),
                longitude=coord.get("longitude"),
                rating=rating,
                review_count=review_count,
                check_in=check_in,
                check_out=check_out,
                nights=nights,
                total_price=amount,
                price_currency=currency,
                price_display=price_display,
                image_url=image_url,
            )
        )

    cursor_strings = [c for c in cursors if isinstance(c, str)]
    return listings, cursor_strings


def _build_search_url(
    *,
    bbox: BoundingBox,
    check_in: str,
    check_out: str,
    adults: int,
    min_bedrooms: int,
    min_bathrooms: int,
    cursor: str | None,
    place_label: str,
) -> str:
    """Build the search URL.

    Note: price_min/price_max are intentionally NOT passed as URL params.
    When Airbnb's server-side price filter is active, bathroom counts are
    dropped from the search card response entirely. We filter by price
    client-side to keep the response complete.
    """
    qs: dict[str, Any] = {
        "checkin": check_in,
        "checkout": check_out,
        "adults": adults,
        "ne_lat": bbox.ne_lat,
        "ne_lng": bbox.ne_lng,
        "sw_lat": bbox.sw_lat,
        "sw_lng": bbox.sw_lng,
        "search_by_map": "true",
        "zoom_level": 12,
        "tab_id": "home_tab",
    }
    if min_bedrooms:
        qs["min_bedrooms"] = min_bedrooms
    if min_bathrooms:
        qs["min_bathrooms"] = min_bathrooms
    if cursor:
        qs["pagination_search"] = "true"
        qs["cursor"] = cursor

    slug = re.sub(r"[^a-zA-Z0-9]+", "-", place_label).strip("-") or "search"
    return f"{AIRBNB_BASE}/s/{slug}/homes?{urlencode(qs)}"


def _fetch_search_page(url: str, proxy_url: str = "") -> dict:
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
    r = requests.get(
        url,
        impersonate="chrome124",
        headers={"Accept-Language": "en"},
        proxies=proxies,
        timeout=30,
    )
    r.raise_for_status()
    m = _SCRIPT_RE.search(r.text)
    if not m:
        raise RuntimeError("Airbnb search page did not contain expected JSON state")
    return json.loads(m.group(1))


_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str | None) -> str:
    if not text:
        return ""
    return _HTML_TAG_RE.sub(" ", text).replace("\xa0", " ").replace("&nbsp;", " ").strip()


def _coerce_listing_id(room_url_or_id: str) -> str:
    m = re.search(r"/rooms/(\d+)", room_url_or_id)
    if m:
        return m.group(1)
    if room_url_or_id.isdigit():
        return room_url_or_id
    raise ValueError(f"Cannot extract listing ID from {room_url_or_id!r}")


def _parse_listing_details(payload: dict, listing_id: str) -> ListingDetails:
    try:
        data = payload["niobeClientData"][0][1]["data"]
        sections_list = data["presentation"]["stayProductDetailPage"]["sections"]["sections"]
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"Unexpected Airbnb listing response shape: {e}") from e

    by_id = {s["sectionId"]: (s.get("section") or {}) for s in sections_list if s.get("sectionId")}
    node = data.get("node") or {}

    title_sec = by_id.get("TITLE_DEFAULT") or {}
    desc_sec = by_id.get("DESCRIPTION_DEFAULT") or {}
    amen_sec = by_id.get("AMENITIES_DEFAULT") or {}
    host_sec = by_id.get("MEET_YOUR_HOST") or {}
    rev_sec = by_id.get("REVIEWS_DEFAULT") or {}
    loc_sec = by_id.get("LOCATION_DEFAULT") or {}
    pol_sec = by_id.get("POLICIES_DEFAULT") or {}
    book_sec = by_id.get("BOOK_IT_SIDEBAR") or {}
    sleep_sec = by_id.get("SLEEPING_ARRANGEMENT_WITH_IMAGES") or {}
    hl_sec = by_id.get("HIGHLIGHTS_DEFAULT") or {}

    description = _strip_html((desc_sec.get("htmlDescription") or {}).get("htmlText"))

    sleeping = [
        f"{ad.get('title')}: {ad.get('subtitle')}".strip(": ").strip()
        for ad in (sleep_sec.get("arrangementDetails") or [])
        if ad.get("title") or ad.get("subtitle")
    ]

    available, unavailable = [], []
    for group in amen_sec.get("seeAllAmenitiesGroups") or []:
        for a in group.get("amenities") or []:
            title = a.get("title")
            if not title:
                continue
            if a.get("available"):
                available.append(title)
            else:
                unavailable.append(title)

    card = host_sec.get("cardData") or {}
    host_review_count = None
    for stat in card.get("stats") or []:
        if stat.get("type") == "REVIEW_COUNT":
            with contextlib.suppress(ValueError, AttributeError):
                host_review_count = int((stat.get("value") or "").replace(",", ""))

    rating_breakdown = {}
    for cat in rev_sec.get("ratings") or []:
        label = cat.get("label")
        rating_str = cat.get("localizedRating")
        if label and rating_str:
            rating_breakdown[label] = rating_str

    house_rules = [
        r.get("title")
        for r in (pol_sec.get("houseRules") or [])
        if r.get("title")
    ]

    highlights = [
        {"title": h.get("title"), "subtitle": h.get("subtitle")}
        for h in (hl_sec.get("highlights") or [])
        if h.get("title") or h.get("subtitle")
    ]

    image_urls: list[str] = []
    seen_uris: set[str] = set()
    hero_sec = by_id.get("HERO_DEFAULT") or {}
    for img in hero_sec.get("previewImages") or []:
        uri = img.get("baseUrl")
        if uri and uri not in seen_uris:
            seen_uris.add(uri)
            image_urls.append(uri)
    for stop in ((node.get("pdpPresentation") or {}).get("mediaTour") or {}).get("stops") or []:
        for item in stop.get("items") or []:
            uri = (item.get("image") or {}).get("uri")
            if uri and uri not in seen_uris:
                seen_uris.add(uri)
                image_urls.append(uri)

    return ListingDetails(
        listing_id=listing_id,
        url=f"{AIRBNB_BASE}/rooms/{listing_id}",
        title=title_sec.get("title") or "",
        description=description,
        max_guests=book_sec.get("maxGuestCapacity"),
        sleeping_arrangements=sleeping,
        location_subtitle=loc_sec.get("subtitle"),
        latitude=loc_sec.get("lat"),
        longitude=loc_sec.get("lng"),
        host_name=card.get("name"),
        host_is_superhost=bool(card.get("isSuperhost")),
        host_is_verified=bool(card.get("isVerified")),
        host_about=host_sec.get("about"),
        host_review_count=host_review_count,
        overall_rating=rev_sec.get("overallRating"),
        review_count=rev_sec.get("overallCount"),
        rating_breakdown=rating_breakdown,
        is_guest_favorite=bool(rev_sec.get("isGuestFavorite")),
        amenities=available,
        unavailable_amenities=unavailable,
        highlights=highlights,
        house_rules=house_rules,
        cancellation_policy=pol_sec.get("cancellationPolicyForDisplay"),
        image_urls=image_urls,
    )


def merge_search_results(results: list[dict[str, Any]], max_results: int) -> dict[str, Any]:
    """Merge results from multiple check-in dates, keeping each listing's cheapest option.

    Sorts merged listings by total_price ascending (None at the end).
    """
    by_id: dict[str, dict[str, Any]] = {}
    search_area = ""
    for r in results:
        if not search_area and r.get("search_area"):
            search_area = r["search_area"]
        for li in r.get("listings") or []:
            lid = li.get("listing_id")
            if not lid:
                continue
            existing = by_id.get(lid)
            new_price = li.get("total_price")
            if existing is None:
                by_id[lid] = li
                continue
            old_price = existing.get("total_price")
            # Prefer the listing with a real price; among real prices, prefer cheapest.
            if new_price is not None and (
                old_price is None or new_price < old_price
            ):
                by_id[lid] = li

    sorted_listings = sorted(
        by_id.values(),
        key=lambda x: (x.get("total_price") is None, x.get("total_price") or 0),
    )[:max_results]
    return {
        "search_area": search_area,
        "total_returned": len(sorted_listings),
        "listings": sorted_listings,
    }


def get_listing_details(
    room_url_or_id: str,
    *,
    check_in: str | None = None,
    check_out: str | None = None,
    adults: int = 2,
    proxy_url: str = "",
) -> dict[str, Any]:
    """Fetch full details for a single Airbnb listing.

    Note: this endpoint does not return a price quote. Pricing on the PDP
    is loaded via a separate async API call. Use `search_stays` to get
    pricing for specific dates, or follow the returned `url` to airbnb.com.
    """
    listing_id = _coerce_listing_id(room_url_or_id)
    qs: dict[str, Any] = {"adults": adults}
    if check_in:
        qs["checkin"] = check_in
    if check_out:
        qs["checkout"] = check_out
    url = f"{AIRBNB_BASE}/rooms/{listing_id}?{urlencode(qs)}"

    payload = _fetch_search_page(url, proxy_url=proxy_url)
    return _parse_listing_details(payload, listing_id).to_dict()


def search_stays(
    *,
    city: str | None = None,
    bbox: BoundingBox | None = None,
    check_in: str | None = None,
    check_out: str | None = None,
    nights: int | None = None,
    adults: int = 2,
    min_bedrooms: int = 0,
    min_bathrooms: int = 0,
    price_min: int = 0,
    price_max: int = 0,
    max_results: int = 50,
    proxy_url: str = "",
) -> dict[str, Any]:
    """Search Airbnb stays in a city or bbox.

    Returns {"listings": [...], "search_area": "...", "total_returned": N}.
    Either `city` or `bbox` must be provided. Either `check_out` or `nights`
    must be provided alongside `check_in`.
    """
    if not check_in:
        raise ValueError("check_in is required (YYYY-MM-DD)")

    ci = date.fromisoformat(check_in)
    if check_out:
        co = date.fromisoformat(check_out)
    elif nights is not None and nights > 0:
        co = ci + timedelta(days=nights)
    else:
        raise ValueError("Provide either check_out or nights")
    night_count = (co - ci).days
    if night_count <= 0:
        raise ValueError("check_out must be after check_in")

    if bbox is None:
        if not city:
            raise ValueError("Provide either city or bbox")
        bbox = geocode_city(city)

    place_label = city or bbox.display_name
    page_idx = 0
    cursors: list[str] = []
    seen_ids: set[str] = set()
    all_listings: list[Listing] = []

    while len(all_listings) < max_results:
        cursor = cursors[page_idx] if page_idx > 0 and page_idx < len(cursors) else None
        if page_idx > 0 and cursor is None:
            break

        url = _build_search_url(
            bbox=bbox,
            check_in=ci.isoformat(),
            check_out=co.isoformat(),
            adults=adults,
            min_bedrooms=min_bedrooms,
            min_bathrooms=min_bathrooms,
            cursor=cursor,
            place_label=place_label,
        )
        payload = _fetch_search_page(url, proxy_url=proxy_url)
        page_listings, cursors = _parse_search_results(
            payload, ci.isoformat(), co.isoformat(), night_count
        )

        new_count = 0
        page_had_listings = bool(page_listings)
        for li in page_listings:
            if li.listing_id in seen_ids:
                continue
            seen_ids.add(li.listing_id)
            if price_min and (li.total_price is None or li.total_price < price_min * night_count):
                continue
            if price_max and (li.total_price is None or li.total_price > price_max * night_count):
                continue
            all_listings.append(li)
            new_count += 1
            if len(all_listings) >= max_results:
                break

        if not page_had_listings or page_idx + 1 >= len(cursors):
            break
        page_idx += 1

    return {
        "search_area": bbox.display_name,
        "total_returned": len(all_listings),
        "listings": [li.to_dict() for li in all_listings],
    }
