"""Minimal Sun Realty vacation rental search client.

Strategy: Sun Realty is a Bluetent/Rezfusion-powered Drupal site. Two endpoints
are used:

  1. Search: GET /solr/?wt=json&fq=sm_nid$rc_core_term_town$name:"Town"&...
     The Drupal Solr index is publicly accessible and returns structured JSON.
     It contains name, URL, beds, baths (full count + 0.5 per half), sleeps,
     featured amenities, teaser images, and location data for all 600+ listings.
     No session or auth token is required.

  2. Detail: GET /outer-banks/<town-slug>/<location-type>/<property-code>
     Server-rendered HTML page parsed with BeautifulSoup. Key selectors:
       - div.field-name-title             → property name
       - div.rc-lodging-beds              → "Bedrooms: N"
       - div.rc-lodging-baths             → "Bathrooms: N" or "N & M Half"
       - div.field-name-field-town        → plain town name (e.g. "Carova")
       - div.field-name-rc-core-term-community → community/subdivision
       - div.field-name-body              → description (first match)
       - div.group-vr-property-amenities  → amenities section containing item-list divs
       - img[src*=rezfusion], img[data-src*=rezfusion] → property photos
       - rcItemAvailForm JSON in <script>  → availability windows

     The pricing API (/rescms/ajax/item/pricing/simple) requires a Drupal
     session cookie that is not easily obtained without a browser. Per-week
     pricing is therefore not available and is intentionally deferred.

Town names (from Solr facets, not slugs):
  Duck (116), Corolla (94), Kill Devil Hills (93), South Nags Head (92),
  Nags Head (64), Avon (43), Kitty Hawk (33), Salvo (22),
  Carova / 4x4 Beaches (17), Rodanthe (13), Southern Shores (13),
  Hatteras (12), Waves (5), Manteo (1).

Property codes are alphanumeric (e.g. "SWB-36", "110-D", "14-E"). The _coerce_id
function accepts bare property codes, numeric item_ids (str or int), and full URLs.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from typing import Any

from bs4 import BeautifulSoup
from curl_cffi import requests

_BASE = "https://www.sunrealtync.com"
_SOLR_URL = f"{_BASE}/solr/"

SUNREALTY_PROXY = os.environ.get("SUNREALTY_PROXY_URL", "")

# Map normalised slug → Solr town display name (from Solr facets, 2026-05).
TOWN_NAMES: dict[str, str] = {
    "duck": "Duck",
    "corolla": "Corolla",
    "kill-devil-hills": "Kill Devil Hills",
    "south-nags-head": "South Nags Head",
    "nags-head": "Nags Head",
    "avon": "Avon",
    "kitty-hawk": "Kitty Hawk",
    "salvo": "Salvo",
    "carova": "Carova / 4x4 Beaches",
    "4x4": "Carova / 4x4 Beaches",
    "rodanthe": "Rodanthe",
    "southern-shores": "Southern Shores",
    "hatteras": "Hatteras",
    "waves": "Waves",
    "manteo": "Manteo",
}

_SOLR_FIELDS = ",".join(
    [
        "item_id",
        "is_eid",
        "ss_name",
        "ss_url",
        "is_nid$field_beds",
        "fs_rc_core_lodging_product$baths",
        "is_rc_core_lodging_product$occ_total",
        "sm_nid$rc_core_term_town$name",
        "sm_nid$rc_core_term_distance_to_beach$name",
        "sm_nid$rc_core_term_featured_amenities$name",
        "sm_nid$rc_core_term_community$name",
        "ss_vrweb_default_image",
        "sm_rc_core_item_teaser_slideshow",
    ]
)

_INT_RE = re.compile(r"(\d+)")
_HTML_TAG_RE = re.compile(r"<[^>]+>")

# The rcItemAvailForm JSON blob embedded in each detail page.
_AVAIL_FORM_RE = re.compile(r'"rcItemAvailForm"\s*:\s*(\[)', re.DOTALL)


@dataclass
class RentalListing:
    listing_id: str
    url: str
    name: str
    bedrooms: int | None
    bathrooms_full: int | None
    bathrooms_half: int | None
    sleeps: int | None
    town: str
    community: str | None
    distance_to_beach: str | None
    featured_amenities: list[str]
    image_url: str | None
    check_in: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AvailabilityWindow:
    start: str
    end: str
    available: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RentalDetails:
    listing_id: str
    url: str
    name: str
    town: str
    community: str | None
    bedrooms: int | None
    bathrooms_full: int | None
    bathrooms_half: int | None
    sleeps: int | None
    description: str
    amenities: list[str]
    image_urls: list[str]
    availability_windows: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _proxies() -> dict[str, str] | None:
    return {"http": SUNREALTY_PROXY, "https": SUNREALTY_PROXY} if SUNREALTY_PROXY else None


def _strip_html(text: str | None) -> str:
    if not text:
        return ""
    return _HTML_TAG_RE.sub(" ", text).replace("\xa0", " ").replace("&nbsp;", " ").strip()


def _parse_baths_float(baths: float | None) -> tuple[int | None, int | None]:
    """Convert Solr baths float to (full, half).

    The Solr field stores the total as a float where .5 represents one half bath
    (e.g. 3.5 → 3 full + 1 half). This matches what the detail page renders as
    'Bathrooms: 3 & 1 Half'.
    """
    if baths is None:
        return None, None
    full = int(baths)
    half = 1 if (baths - full) >= 0.4 else 0
    return full, half


def _parse_baths_text(baths_text: str | None) -> tuple[int | None, int | None]:
    """Parse 'Bathrooms: 3 & 1 Half' or 'Bathrooms: 2' → (full, half)."""
    if not baths_text:
        return None, None
    numbers = _INT_RE.findall(baths_text)
    if not numbers:
        return None, None
    full = int(numbers[0])
    half = int(numbers[1]) if len(numbers) > 1 and "half" in baths_text.lower() else 0
    return full, half


def _coerce_id(rental_url_or_id: str | int) -> str:
    """Normalise any form of Sun Realty identifier to a canonical lookup key.

    Accepts:
    - A bare int or numeric string: 655, "655"  → item_id for Solr
    - A full canonical URL: "https://www.sunrealtync.com/outer-banks/..."
    - A bare property code string: "SWB-36", "swb-36", "14-E"

    Returns a string that is either:
    - A pure-digit string (numeric item_id): use Solr q=item_id:<n>
    - A URL path or full URL: fetch directly
    - A property code: use Solr q=ss_url:*<code_lower>
    """
    if isinstance(rental_url_or_id, int):
        return str(rental_url_or_id)
    stripped = rental_url_or_id.strip()
    if stripped.isdigit():
        return stripped
    if stripped.startswith("http") or stripped.startswith("/outer-banks"):
        return stripped
    # Treat as a property code (alphanumeric slug like "SWB-36").
    # Normalize to lowercase for URL matching.
    return stripped.lower()


def _resolve_detail_url(identifier: str) -> str:
    """Resolve any identifier to a full detail page URL.

    Queries Solr when identifier is a numeric item_id or property code.
    Returns the URL directly when identifier is already a URL.
    """
    if identifier.startswith("http"):
        return identifier
    if identifier.startswith("/outer-banks"):
        return f"{_BASE}{identifier}"

    # Build Solr query
    q = f"item_id:{identifier}" if identifier.isdigit() else f"ss_url:*{identifier}"

    r = requests.get(
        _SOLR_URL,
        impersonate="chrome124",
        headers={"Accept": "application/json"},
        proxies=_proxies(),
        params={"q": q, "rows": "1", "wt": "json", "fl": "ss_url"},
        timeout=30,
    )
    r.raise_for_status()
    docs = r.json().get("response", {}).get("docs", [])
    if not docs or not docs[0].get("ss_url"):
        raise ValueError(f"No Sun Realty listing found for identifier {identifier!r}")
    return docs[0]["ss_url"]


def _parse_solr_doc(doc: dict) -> RentalListing:
    """Parse a single Solr document into a RentalListing."""
    item_id = str(doc.get("item_id") or doc.get("is_eid") or "")
    if not item_id:
        raise RuntimeError("Unexpected Sun Realty response shape: missing item_id in Solr doc")

    baths_float = doc.get("fs_rc_core_lodging_product$baths")
    baths_full, baths_half = _parse_baths_float(baths_float)

    towns = doc.get("sm_nid$rc_core_term_town$name") or []
    town = towns[0] if towns else ""

    communities = doc.get("sm_nid$rc_core_term_community$name") or []
    community = communities[0] if communities else None

    distances = doc.get("sm_nid$rc_core_term_distance_to_beach$name") or []
    distance_to_beach = distances[0] if distances else None

    featured = doc.get("sm_nid$rc_core_term_featured_amenities$name") or []

    images = doc.get("sm_rc_core_item_teaser_slideshow") or []
    image_url = images[0] if images else doc.get("ss_vrweb_default_image")

    return RentalListing(
        listing_id=item_id,
        url=doc.get("ss_url") or "",
        name=doc.get("ss_name") or "",
        bedrooms=doc.get("is_nid$field_beds"),
        bathrooms_full=baths_full,
        bathrooms_half=baths_half,
        sleeps=doc.get("is_rc_core_lodging_product$occ_total"),
        town=town,
        community=community,
        distance_to_beach=distance_to_beach,
        featured_amenities=list(featured),
        image_url=image_url,
        check_in="",
    )


def _parse_search_results(payload: dict, check_in: str = "") -> list[RentalListing]:
    """Parse the /solr/ response into a list of RentalListings."""
    response = payload.get("response")
    if response is None:
        raise RuntimeError(
            "Unexpected Sun Realty response shape: missing 'response' key in Solr JSON"
        )
    docs = response.get("docs")
    if docs is None:
        raise RuntimeError(
            "Unexpected Sun Realty response shape: missing 'docs' key in Solr response"
        )

    listings: list[RentalListing] = []
    for doc in docs:
        try:
            li = _parse_solr_doc(doc)
        except RuntimeError:
            continue
        li.check_in = check_in
        listings.append(li)
    return listings


def _parse_avail_form(text: str) -> list[AvailabilityWindow]:
    """Extract the rcItemAvailForm availability windows from a detail page."""
    m = _AVAIL_FORM_RE.search(text)
    if not m:
        return []

    start_bracket = m.start(1)
    depth = 0
    pos = start_bracket
    while pos < len(text):
        if text[pos] == "[":
            depth += 1
        elif text[pos] == "]":
            depth -= 1
            if depth == 0:
                break
        pos += 1
    raw = text[start_bracket : pos + 1]

    try:
        config_list = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return []

    if not config_list:
        return []

    avail_raw = config_list[0].get("avail") or []
    windows: list[AvailabilityWindow] = []
    for entry in avail_raw:
        start = entry.get("b") or ""
        end = entry.get("e") or ""
        available = str(entry.get("a", "0")) == "1"
        if start and end:
            windows.append(AvailabilityWindow(start=start, end=end, available=available))
    return windows


def _parse_detail_page(html: str, url: str) -> RentalDetails:
    """Parse a Sun Realty property detail page into a RentalDetails."""
    soup = BeautifulSoup(html, "html.parser")

    title_div = soup.find("div", class_=lambda c: c and "field-name-title" in c)
    if title_div is None:
        raise RuntimeError(
            f"Unexpected Sun Realty response shape: no title div on detail page {url!r}"
        )
    name = title_div.get_text(strip=True)

    beds_div = soup.find("div", class_="rc-lodging-beds")
    bedrooms: int | None = None
    if beds_div:
        m = _INT_RE.search(beds_div.get_text(strip=True))
        bedrooms = int(m.group(1)) if m else None

    baths_div = soup.find("div", class_="rc-lodging-baths")
    baths_full, baths_half = _parse_baths_text(
        baths_div.get_text(strip=True) if baths_div else None
    )

    # Prefer explicit town field over community field.
    town_div = soup.find("div", class_=lambda c: c and "field-name-field-town" in c)
    community_div = soup.find(
        "div", class_=lambda c: c and "field-name-rc-core-term-community" in c
    )
    town = town_div.get_text(strip=True) if town_div else ""
    community = community_div.get_text(strip=True) if community_div else None

    # First field-name-body div that has substantial content is the description.
    description = ""
    for body_div in soup.find_all("div", class_=lambda c: c and "field-name-body" in c):
        txt = body_div.get_text(separator=" ", strip=True)
        if len(txt) > 80:
            description = txt
            break

    # Amenities: all item-list divs following the "Amenities & Beds" h3.
    amenities: list[str] = []
    amen_section = soup.find("div", class_=lambda c: c and "group-vr-property-amenities" in c)
    if amen_section:
        amen_h3 = amen_section.find("h3", string=re.compile("Amenities", re.IGNORECASE))
        if amen_h3:
            current = amen_h3.find_next_sibling()
            while current:
                if current.name == "h3":
                    break
                if current.name == "div" and "item-list" in (current.get("class") or []):
                    for li in current.find_all("li"):
                        txt = li.get_text(strip=True)
                        if txt:
                            amenities.append(txt)
                current = current.find_next_sibling()

    # Images: collect unique rezfusion URLs from src and data-src attributes.
    seen_urls: set[str] = set()
    image_urls: list[str] = []
    for img in soup.find_all("img"):
        for attr in ("src", "data-src"):
            val = img.get(attr, "")
            if "rezfusion" in val and val not in seen_urls:
                seen_urls.add(val)
                image_urls.append(val)

    availability_windows = _parse_avail_form(html)

    # Extract item_id from the page for the listing_id field.
    item_id = ""
    for m in re.finditer(r'"item_id"\s*:\s*"?(\d+)"?', html):
        item_id = m.group(1)
        break
    if not item_id:
        # Fall back to eid in rcItemAvailForm
        for m in re.finditer(r'"eid"\s*:\s*"?(\d+)"?', html):
            item_id = m.group(1)
            break

    return RentalDetails(
        listing_id=item_id,
        url=url,
        name=name,
        town=town,
        community=community,
        bedrooms=bedrooms,
        bathrooms_full=baths_full,
        bathrooms_half=baths_half,
        sleeps=None,
        description=description,
        amenities=amenities,
        image_urls=image_urls,
        availability_windows=[w.to_dict() for w in availability_windows],
    )


def _fetch_html(url: str) -> str:
    r = requests.get(
        url,
        impersonate="chrome124",
        headers={"Accept-Language": "en"},
        proxies=_proxies(),
        timeout=30,
    )
    r.raise_for_status()
    return r.text


def search_rentals(
    town: str,
    min_bedrooms: int = 0,
    max_results: int = 50,
    check_in: str = "",
) -> dict[str, Any]:
    """Fetch active Sun Realty rentals for a given OBX town.

    Returns {"search_area", "total_returned", "listings"}.

    Each listing includes: listing_id, url, name, bedrooms, bathrooms_full,
    bathrooms_half, sleeps, town, community, distance_to_beach,
    featured_amenities, image_url, check_in.

    The Solr index returns all results in one call (no pagination). max_results
    caps the returned list after bedroom filtering.

    Per-week pricing is NOT available via the Solr API. The availability API
    requires a Drupal session and is not surfaced here. Use get_rental_details
    to obtain the availability windows embedded in the detail page.

    check_in: stored on each listing for reference but does not change the
    results or pricing since the Solr endpoint is date-agnostic.
    """
    town_slug = town.strip().lower()
    town_display = TOWN_NAMES.get(town_slug)
    if town_display is None:
        valid = ", ".join(sorted(TOWN_NAMES))
        raise ValueError(f"Unknown town {town!r}. Valid towns: {valid}")

    params: dict[str, Any] = {
        "wt": "json",
        "rows": "999",
        "fl": _SOLR_FIELDS,
        "fq": f'sm_nid$rc_core_term_town$name:"{town_display}"',
    }

    r = requests.get(
        _SOLR_URL,
        impersonate="chrome124",
        headers={"Accept": "application/json", "Accept-Language": "en"},
        proxies=_proxies(),
        params=params,
        timeout=30,
    )
    r.raise_for_status()
    payload = r.json()

    all_listings = _parse_search_results(payload, check_in)
    filtered = [li for li in all_listings if (li.bedrooms or 0) >= min_bedrooms]
    capped = filtered[:max_results]

    return {
        "search_area": f"{town_display}, NC (Outer Banks) - Sun Realty",
        "total_returned": len(capped),
        "listings": [li.to_dict() for li in capped],
    }


def get_rental_details(rental_url_or_id: str | int) -> dict[str, Any]:
    """Fetch full details for a single Sun Realty property.

    Accepts:
    - Numeric item_id (int or str): 655, "655"
    - Property code string: "SWB-36", "swb-36"
    - Canonical URL: "https://www.sunrealtync.com/outer-banks/..."

    Returns {listing_id, url, name, town, community, bedrooms, bathrooms_full,
    bathrooms_half, sleeps (always None — not surfaced in HTML), description,
    amenities, image_urls, availability_windows}.

    availability_windows is a list of {start, end, available} from the
    rcItemAvailForm JSON embedded in the detail page. available=True means the
    dates are open for booking. Per-week pricing requires a Drupal session
    (not implemented — deferred).
    """
    identifier = _coerce_id(rental_url_or_id)
    detail_url = _resolve_detail_url(identifier)
    html = _fetch_html(detail_url)
    return _parse_detail_page(html, detail_url).to_dict()
