"""Minimal Redfin search client.

Strategy — both search and detail pages use the same extraction path:

    root.__reactServerState.InitialContext = { "ReactServerAgent.cache": { "dataCache": {...} } }

The value is a JS object literal assigned in a <script> tag. We locate the assignment,
walk brace-depth to find the matching closing brace, then JSON-parse.

Search (GET /zipcode/<zip>):
    Cache key matching "/stingray/api/gis?" → payload.homes[] — each home has
    beds, baths (float), price.value, sqFt.value, lotSize.value, yearBuilt.value, dom.value,
    hoa.value (optional), url (relative path), city, state, zip, listingId (numeric),
    propertyId (numeric), mlsId.value, dataSourceId, photoFormat.
    Image URL = https://ssl.cdn-redfin.com/photo/{dataSourceId}/bigphoto/{mlsId[-3:]}/{mlsId}_0.{fmt}

Detail (GET <home_url>):
    Cache key "/stingray/api/home/details/aboveTheFold" → payload.addressSectionInfo for
    beds, baths, price, sqft, year_built, lot_size, address parts;
    payload.mediaBrowserInfo.photos for image URLs (photos[*].photoUrls.fullScreenPhotoUrl).
    Cache key "/stingray/api/home/details/mainHouseInfoPanelInfo" →
    payload.mainHouseInfo.listingAgents for listing agent name and broker.
    JSON-LD block with @type containing "RealEstateListing" for description text.
    HOA not available on the detail page without an extra authenticated call; always None.

Schema-drift breadcrumb:
    If Redfin restructures the stingray API or changes the ReactServerAgent key names, the
    _parse_* functions raise RuntimeError. Most likely breakage points:
      - ReactServerAgent.cache key name change
      - "{}&&" prefix removed or changed
      - homes[] moving inside a different payload key
      - aboveTheFold splitting into further sub-calls
"""

from __future__ import annotations

import html as _html
import json
import re
from dataclasses import asdict, dataclass
from typing import Any

from curl_cffi import requests

REDFIN_BASE = "https://www.redfin.com"

_RSS_START = "root.__reactServerState.InitialContext = "

_LISTING_ID_RE = re.compile(r"/home/(\d+)")


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class HomeSearchResult:
    listing_id: str
    url: str
    address: str
    city: str
    state: str
    zip: str
    price: float | None
    bedrooms: int | None
    bathrooms: float | None
    building_sqft: int | None
    lot_sqft: int | None
    year_built: int | None
    image_url: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HomeDetails:
    listing_id: str
    url: str
    address: str
    city: str
    state: str
    zip: str
    price: float | None
    bedrooms: int | None
    bathrooms: float | None
    building_sqft: int | None
    lot_sqft: int | None
    year_built: int | None
    description: str | None
    image_urls: list[str]
    listing_agent: str | None
    listing_brokerage: str | None
    days_on_market: int | None
    hoa_fee: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _coerce_id(home_url_or_id: str | int) -> str:
    """Return the numeric listing ID string from a URL or bare int/str."""
    if isinstance(home_url_or_id, int):
        return str(home_url_or_id)
    s = str(home_url_or_id).strip()
    m = _LISTING_ID_RE.search(s)
    if m:
        return m.group(1)
    if s.isdigit():
        return s
    raise ValueError(f"Cannot extract Redfin listing ID from {home_url_or_id!r}")


def _extract_rss_json(html: str) -> dict[str, Any]:
    """Extract and parse the ReactServerState InitialContext JSON block.

    Redfin sets this as a JS assignment so we can't use a simple regex — we
    walk brace depth from the opening '{' to find the matching closing brace.
    The assignment ends with '};' but the JSON itself is well-formed up to that
    closing brace.
    """
    idx = html.find(_RSS_START)
    if idx == -1:
        raise RuntimeError(
            "Unexpected Redfin response shape: __reactServerState.InitialContext not found"
        )
    after = html[idx + len(_RSS_START) :]
    brace_start = after.find("{")
    if brace_start == -1:
        raise RuntimeError(
            "Unexpected Redfin response shape: no opening brace in InitialContext"
        )
    segment = after[brace_start:]

    depth = 0
    end_pos = 0
    in_string = False
    escape_next = False
    for i, ch in enumerate(segment):
        if escape_next:
            escape_next = False
            end_pos = i
            continue
        if in_string:
            if ch == "\\":
                escape_next = True
            elif ch == '"':
                in_string = False
            end_pos = i
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end_pos = i
                break
        end_pos = i

    try:
        return json.loads(segment[: end_pos + 1])
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Unexpected Redfin response shape: __reactServerState payload is not valid JSON ({e})"
        ) from e


def _get_cache(rss: dict[str, Any]) -> dict[str, Any]:
    try:
        return rss["ReactServerAgent.cache"]["dataCache"]
    except (KeyError, TypeError) as e:
        raise RuntimeError(f"Unexpected Redfin response shape: {e}") from e


def _decode_cache_entry(entry: dict[str, Any]) -> dict[str, Any] | None:
    """Parse one dataCache entry's text payload (strips Redfin's '{}&&' prefix).

    Returns the 'payload' sub-dict, or None if the entry lacks usable data.
    """
    res = entry.get("res")
    if not isinstance(res, dict):
        return None
    text_val = res.get("text")
    if not isinstance(text_val, str) or len(text_val) < 5:
        return None
    # Redfin wraps every JSON response in "{}&&" to prevent JSON hijacking.
    clean = text_val[len("{}&&") :].strip() if text_val.startswith("{}&&") else text_val.strip()
    if not clean or not clean.startswith("{"):
        return None
    try:
        return json.loads(clean).get("payload")
    except (json.JSONDecodeError, AttributeError):
        return None


def _cache_payload(cache: dict[str, Any], key_substr: str) -> dict[str, Any] | None:
    """Return the decoded payload for the first cache key containing key_substr."""
    for k, v in cache.items():
        if key_substr in k and isinstance(v, dict):
            return _decode_cache_entry(v)
    return None


def _image_url_from_home(home: dict[str, Any]) -> str | None:
    """Construct primary photo URL from a gis homes[] entry.

    Pattern confirmed live:
    https://ssl.cdn-redfin.com/photo/{dataSourceId}/bigphoto/{mlsId[-3:]}/{mlsId}_0.{photoFormat}
    """
    mls_id = (home.get("mlsId") or {}).get("value")
    data_source_id = home.get("dataSourceId")
    photo_format = home.get("photoFormat")
    if not mls_id or not data_source_id or not photo_format:
        return None
    subdir = str(mls_id)[-3:]
    return (
        f"https://ssl.cdn-redfin.com/photo/{data_source_id}"
        f"/bigphoto/{subdir}/{mls_id}_0.{photo_format}"
    )


def _extract_description_from_html(html: str) -> str | None:
    """Extract description from the JSON-LD RealEstateListing block."""
    for m in re.finditer(
        r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL
    ):
        try:
            d = json.loads(m.group(1))
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(d, dict):
            continue
        types = d.get("@type") or []
        if isinstance(types, str):
            types = [types]
        if "RealEstateListing" in types or "Product" in types:
            raw = d.get("description")
            if raw:
                return _html.unescape(raw).strip()
    return None


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


def _parse_search_results(cache: dict[str, Any]) -> list[HomeSearchResult]:
    """Parse homes[] from the /stingray/api/gis cache entry."""
    payload = _cache_payload(cache, "/stingray/api/gis?")
    if payload is None:
        raise RuntimeError(
            "Unexpected Redfin response shape: /stingray/api/gis cache entry missing"
        )
    homes_raw = payload.get("homes")
    if not isinstance(homes_raw, list):
        raise RuntimeError(
            "Unexpected Redfin response shape: payload.homes is not a list"
        )

    results: list[HomeSearchResult] = []
    for h in homes_raw:
        if not isinstance(h, dict):
            continue
        listing_id = str(h.get("propertyId") or h.get("listingId") or "")
        url_path = h.get("url") or ""
        # URL path is the canonical source — extract propertyId from /home/<id>
        pid_m = _LISTING_ID_RE.search(url_path)
        if pid_m:
            listing_id = pid_m.group(1)
        if not listing_id:
            continue

        price_obj = h.get("price") or {}
        price_val = price_obj.get("value") if isinstance(price_obj, dict) else None
        price = float(price_val) if price_val is not None else None

        sqft_obj = h.get("sqFt") or {}
        sqft_val = sqft_obj.get("value") if isinstance(sqft_obj, dict) else None
        building_sqft = int(sqft_val) if sqft_val is not None else None

        lot_obj = h.get("lotSize") or {}
        lot_val = lot_obj.get("value") if isinstance(lot_obj, dict) else None
        lot_sqft = int(lot_val) if lot_val is not None else None

        year_obj = h.get("yearBuilt") or {}
        year_val = year_obj.get("value") if isinstance(year_obj, dict) else None
        year_built = int(year_val) if year_val is not None else None

        beds_raw = h.get("beds")
        bedrooms = int(beds_raw) if beds_raw is not None else None

        baths_raw = h.get("baths")
        bathrooms = float(baths_raw) if baths_raw is not None else None

        street = (h.get("streetLine") or {}).get("value") or ""
        unit = (h.get("unitNumber") or {}).get("value") or ""
        address = f"{street} {unit}".strip() if unit else street

        results.append(
            HomeSearchResult(
                listing_id=listing_id,
                url=REDFIN_BASE + url_path if url_path else "",
                address=address,
                city=h.get("city") or "",
                state=h.get("state") or "",
                zip=h.get("zip") or "",
                price=price,
                bedrooms=bedrooms,
                bathrooms=bathrooms,
                building_sqft=building_sqft,
                lot_sqft=lot_sqft,
                year_built=year_built,
                image_url=_image_url_from_home(h),
            )
        )
    return results


def _parse_home_details(
    cache: dict[str, Any], html: str, listing_id: str, page_url: str
) -> HomeDetails:
    """Parse home details from aboveTheFold, mainHouseInfoPanelInfo, and JSON-LD."""
    atf_payload = _cache_payload(cache, "/stingray/api/home/details/aboveTheFold")
    if atf_payload is None:
        raise RuntimeError(
            "Unexpected Redfin response shape: "
            "/stingray/api/home/details/aboveTheFold cache entry missing"
        )

    if "addressSectionInfo" not in atf_payload:
        raise RuntimeError(
            "Unexpected Redfin response shape: "
            "addressSectionInfo missing from aboveTheFold payload"
        )

    addr_info = atf_payload["addressSectionInfo"] or {}
    media_info = atf_payload.get("mediaBrowserInfo") or {}

    price_obj = addr_info.get("priceInfo") or {}
    price = float(price_obj["amount"]) if price_obj.get("amount") is not None else None

    sqft_obj = addr_info.get("sqFt") or {}
    building_sqft = int(sqft_obj["value"]) if sqft_obj.get("value") is not None else None

    lot_sqft_raw = addr_info.get("lotSize")
    lot_sqft = int(lot_sqft_raw) if lot_sqft_raw is not None else None

    year_built_raw = addr_info.get("yearBuilt")
    year_built = int(year_built_raw) if year_built_raw is not None else None

    beds_raw = addr_info.get("beds")
    bedrooms = int(beds_raw) if beds_raw is not None else None

    baths_raw = addr_info.get("baths")
    bathrooms = float(baths_raw) if baths_raw is not None else None

    street_info = addr_info.get("streetAddress") or {}
    address = street_info.get("assembledAddress") or ""
    city = addr_info.get("city") or ""
    state = addr_info.get("state") or ""
    zip_code = addr_info.get("zip") or ""

    # cumulativeDaysOnMarket = 0 means just listed today; None = unknown
    dom_raw = addr_info.get("cumulativeDaysOnMarket")
    days_on_market = int(dom_raw) if dom_raw is not None else None

    # Images from mediaBrowserInfo.photos
    photos_raw = media_info.get("photos") or []
    image_urls: list[str] = []
    seen: set[str] = set()
    for photo in photos_raw:
        if not isinstance(photo, dict):
            continue
        urls = photo.get("photoUrls") or {}
        img_url = urls.get("fullScreenPhotoUrl") or urls.get("nonFullScreenPhotoUrl")
        if img_url and img_url not in seen:
            seen.add(img_url)
            image_urls.append(img_url)

    # Agent/brokerage from mainHouseInfoPanelInfo
    listing_agent: str | None = None
    listing_brokerage: str | None = None
    mhip_payload = _cache_payload(cache, "/stingray/api/home/details/mainHouseInfoPanelInfo")
    if mhip_payload:
        mhi = mhip_payload.get("mainHouseInfo") or {}
        agents = mhi.get("listingAgents") or []
        if agents and isinstance(agents[0], dict):
            agent_info = agents[0].get("agentInfo") or {}
            listing_agent = agent_info.get("agentName") or None
            listing_brokerage = agents[0].get("brokerName") or None

    description = _extract_description_from_html(html)

    return HomeDetails(
        listing_id=listing_id,
        url=page_url,
        address=address,
        city=city,
        state=state,
        zip=zip_code,
        price=price,
        bedrooms=bedrooms,
        bathrooms=bathrooms,
        building_sqft=building_sqft,
        lot_sqft=lot_sqft,
        year_built=year_built,
        description=description,
        image_urls=image_urls,
        listing_agent=listing_agent,
        listing_brokerage=listing_brokerage,
        days_on_market=days_on_market,
        hoa_fee=None,  # HOA not reliably available on detail page; would need extra call
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _fetch_page(url: str, proxy_url: str = "") -> str:
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
    r = requests.get(
        url,
        impersonate="chrome124",
        headers={"Accept-Language": "en"},
        proxies=proxies,
        timeout=30,
    )
    r.raise_for_status()
    return r.text


def search_homes(
    zip_code: str,
    *,
    status: str = "for_sale",
    min_beds: int = 0,
    max_beds: int = 0,
    min_price: int = 0,
    max_price: int = 0,
    max_results: int = 50,
    proxy_url: str = "",
) -> dict[str, Any]:
    """Search Redfin listings in a ZIP code.

    Only 'for_sale' status is supported in MVP. Other values are accepted but
    will still return for-sale listings (the ZIP page defaults to for-sale).
    Returns {"search_area": str, "total_returned": int, "homes": [...]}.
    """
    url = f"{REDFIN_BASE}/zipcode/{zip_code}"
    html = _fetch_page(url, proxy_url=proxy_url)
    rss = _extract_rss_json(html)
    cache = _get_cache(rss)
    homes = _parse_search_results(cache)

    filtered: list[HomeSearchResult] = []
    for h in homes:
        if min_beds and (h.bedrooms is None or h.bedrooms < min_beds):
            continue
        if max_beds and (h.bedrooms is None or h.bedrooms > max_beds):
            continue
        if min_price and (h.price is None or h.price < min_price):
            continue
        if max_price and (h.price is None or h.price > max_price):
            continue
        filtered.append(h)
        if len(filtered) >= max_results:
            break

    return {
        "search_area": f"ZIP {zip_code}",
        "total_returned": len(filtered),
        "homes": [h.to_dict() for h in filtered],
    }


def get_home_details(
    home_url_or_id: str | int,
    *,
    proxy_url: str = "",
) -> dict[str, Any]:
    """Fetch full details for a single Redfin listing.

    Accepts a full redfin.com URL or a bare numeric property/listing ID.
    When only a numeric ID is passed, we attempt a redirect via /home/<id>.
    Full URLs are preferred for reliable off-market lookups.
    """
    if isinstance(home_url_or_id, int) or str(home_url_or_id).strip().isdigit():
        numeric_id = _coerce_id(home_url_or_id)
        page_url = f"{REDFIN_BASE}/home/{numeric_id}"
    else:
        page_url = str(home_url_or_id).strip()
        if not page_url.startswith("http"):
            page_url = REDFIN_BASE + page_url
        numeric_id = _coerce_id(page_url)

    html = _fetch_page(page_url, proxy_url=proxy_url)
    rss = _extract_rss_json(html)
    cache = _get_cache(rss)
    details = _parse_home_details(cache, html, numeric_id, page_url)
    return details.to_dict()
