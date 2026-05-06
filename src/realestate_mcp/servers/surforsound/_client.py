"""Minimal Surf or Sound Realty vacation rental search client.

Strategy: Surf or Sound is a server-rendered ASP.NET / Umbraco CMS site.
Listing cards are returned as HTML fragments from two endpoints:

  1. Search (page 1): GET /search?villages=<slug>&minBedrooms=<n>&checkin=<date>&checkout=<date>
     Returns a full HTML page whose `.sos-search-results-grid` div contains
     the first 24 listing cards plus `total-properties-found` / `page-size`
     data attributes for pagination.

  2. Subsequent pages: GET /umbraco/surface/search/search-results?villages=<slug>
     &minBedrooms=<n>&checkin=<date>&checkout=<date>&page=<n>
     Returns a bare HTML fragment of listing cards (no wrapping page). The
     endpoint and query-param names were discovered by reading
     /dist/app.js (`createSearchQuery` + `getSearchResultsHtml`).

  3. Property detail: GET /hatteras-vacation-rental/property/<id>
     Full HTML page containing:
       - Property name, ID, VILLAGE/BED/BATH/LOCATION stats block
       - `#property-description` div with the listing description
       - `.sos-column-list-3` div for amenities list
       - `data-lazy` image thumbnails in `.sos-gallery__nav-slide` elements
       - `Weekly: $X - $Y` paragraph for rate range
       - `window.Sos.Property.WeeklyAvailabilities` JSON array for per-week rates

BeautifulSoup4 is used for HTML parsing (regex on HTML was too brittle for
the deeply-nested card structure).

Ocracoke: queried and returns 0 results — Surf or Sound does not cover it.

Date params: checkin/checkout are accepted by both endpoints and shift the
displayed weekly price to the selected week. Param names are `checkin` and
`checkout` (YYYY-MM-DD). The search page always defaults to the upcoming
Saturday arrival if dates are omitted.

Pagination: the AJAX endpoint supports `page=N` with a page size of 24.
Per-village result counts are small enough (Avon: ~18, Rodanthe: ~30) that
most single-village queries fit on one page. Multi-page fetch is supported.

Sleeps: not present on either the search card or the detail page. The site
does not surface a sleeps count in its public HTML.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from typing import Any

from bs4 import BeautifulSoup
from curl_cffi import requests

_BASE = "https://www.surforsound.com"
_SEARCH_URL = f"{_BASE}/search"
_AJAX_SEARCH_URL = f"{_BASE}/umbraco/surface/search/search-results"
_DETAIL_URL = f"{_BASE}/hatteras-vacation-rental/property"

SOS_PROXY = os.environ.get("SOS_PROXY_URL", "")

VILLAGE_SLUGS: set[str] = {
    "rodanthe",
    "waves",
    "salvo",
    "avon",
    "buxton",
    "frisco",
    "hatteras",
}

_INT_RE = re.compile(r"(\d+)")
_PRICE_RE = re.compile(r"\$([\d,]+(?:\.\d+)?)")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WEEKLY_AVAIL_RE = re.compile(r"WeeklyAvailabilities\s*=\s*(\[.*?\]);", re.DOTALL)
_WEEKLY_RANGE_RE = re.compile(r"Weekly:\s*\$([\d,]+)\s*-\s*\$([\d,]+)", re.IGNORECASE)


@dataclass
class RentalListing:
    listing_id: int
    url: str
    name: str
    bedrooms: int | None
    bathrooms_full: int | None
    bathrooms_half: int | None
    town: str
    location: str | None
    weekly_rate: float | None
    check_in: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RentalDetails:
    listing_id: int
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
    weekly_rate_min: float | None
    weekly_rate_max: float | None
    weekly_availabilities: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _proxies() -> dict[str, str] | None:
    return {"http": SOS_PROXY, "https": SOS_PROXY} if SOS_PROXY else None


def _strip_html(text: str | None) -> str:
    if not text:
        return ""
    return _HTML_TAG_RE.sub(" ", text).replace("\xa0", " ").replace("&nbsp;", " ").strip()


def _parse_price(price_text: str | None) -> float | None:
    if not price_text:
        return None
    m = _PRICE_RE.search(price_text)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _parse_baths(bath_text: str | None) -> tuple[int | None, int | None]:
    """Parse '8 Full, 2 Half' -> (8, 2) or '3 Full' -> (3, 0)."""
    if not bath_text:
        return None, None
    full_m = re.search(r"(\d+)\s+Full", bath_text, re.IGNORECASE)
    half_m = re.search(r"(\d+)\s+Half", bath_text, re.IGNORECASE)
    full = int(full_m.group(1)) if full_m else None
    half = int(half_m.group(1)) if half_m else 0
    return full, half


def _coerce_id(rental_url_or_id: str | int) -> int:
    """Extract numeric property ID from a URL, bare string, or int.

    Accepts:
    - A bare int: 553
    - A plain integer string: "553"
    - A full detail URL: "https://www.surforsound.com/hatteras-vacation-rental/property/553"
    - A bare path: "/hatteras-vacation-rental/property/553"
    """
    if isinstance(rental_url_or_id, int):
        return rental_url_or_id
    stripped = rental_url_or_id.strip()
    if stripped.isdigit():
        return int(stripped)
    m = re.search(r"/property/(\d+)", stripped)
    if m:
        return int(m.group(1))
    raise ValueError(f"Cannot extract listing ID from {rental_url_or_id!r}")


_VILLAGE_TEXT_RE = re.compile(r"Village\s*:\s*([A-Za-z][A-Za-z\- ]*)", re.IGNORECASE)


def _parse_card(card_tag: Any, check_in: str) -> RentalListing | None:
    """Parse a single `.sos-property-card` BeautifulSoup tag into a RentalListing."""
    prop_url = card_tag.get("data-property-url") or ""
    id_m = re.search(r"/property/(\d+)", prop_url)
    if not id_m:
        return None
    listing_id = int(id_m.group(1))

    name_div = card_tag.find("div", class_=lambda c: c and "sos-property-card_name" in c)
    name = name_div.get_text(strip=True) if name_div else ""
    name = re.sub(r"\s*-\s*#\d+$", "", name).strip()

    details = card_tag.find(
        "div", class_=lambda c: c and "sos-property-card__details" in c
    )
    bedrooms: int | None = None
    baths_full: int | None = None
    baths_half: int | None = None
    town = ""
    location: str | None = None

    if details:
        for p in details.find_all("p", class_="mb-0"):
            label_span = p.find("span", class_=lambda c: c and "sos-letter-spc-1" in c)
            val_span = p.find("span", class_=lambda c: c and "fw-bold" in c)
            if not label_span or not val_span:
                continue
            label = label_span.get_text(strip=True).upper()
            val = val_span.get_text(strip=True)
            if label == "BED":
                m = _INT_RE.match(val)
                bedrooms = int(m.group(1)) if m else None
            elif label == "BATH":
                baths_full, baths_half = _parse_baths(val)
            elif label == "VILLAGE":
                town = val.lower().replace(" ", "-")
            elif label == "LOCATION":
                location = val

    if not town:
        # Real cards put Village in a sibling "d-flex justify-content-around" div with
        # text like "Village: Avon", outside the __details container. The same div
        # often holds an unrelated "Saturday Check in" label in another <small>, so we
        # walk children and only match a <small> that starts with "Village:".
        for div in card_tag.find_all(
            "div", class_=lambda c: c and "justify-content-around" in c
        ):
            for child in div.find_all(["small", "span", "p"]):
                txt = child.get_text(" ", strip=True)
                m = _VILLAGE_TEXT_RE.match(txt)
                if m:
                    town = m.group(1).strip().lower().replace(" ", "-")
                    break
            if town:
                break

    price_span = card_tag.find("span", class_=lambda c: c and "text-info" in c)
    weekly_rate = _parse_price(price_span.get_text(strip=True) if price_span else None)

    base_url = re.sub(r"\?.*$", "", prop_url)

    return RentalListing(
        listing_id=listing_id,
        url=base_url,
        name=name,
        bedrooms=bedrooms,
        bathrooms_full=baths_full,
        bathrooms_half=baths_half,
        town=town,
        location=location,
        weekly_rate=weekly_rate,
        check_in=check_in,
    )


def _parse_search_page(html: str, check_in: str) -> tuple[list[RentalListing], int, int]:
    """Parse HTML (full page or AJAX fragment) into listings + pagination data.

    Returns (listings, total_found, page_size).
    total_found and page_size are 0 when parsing an AJAX fragment (not the first page).
    """
    soup = BeautifulSoup(html, "html.parser")

    grid = soup.find(attrs={"page-size": True})
    if grid is not None:
        total_found = int(grid.get("total-properties-found", 0))
        page_size = int(grid.get("page-size", 24))
    else:
        total_found = 0
        page_size = 24

    cards = soup.find_all("div", class_="sos-property-card")
    if not cards and grid is None:
        card_check = soup.find_all("div", class_=lambda c: c and "sos-property-card" in c)
        if not card_check:
            raise RuntimeError(
                "Unexpected Surf or Sound response shape: "
                "no listing cards found and no search grid container"
            )

    listings: list[RentalListing] = []
    for card in cards:
        parsed = _parse_card(card, check_in)
        if parsed is not None:
            listings.append(parsed)

    return listings, total_found, page_size


def _parse_detail_page(html: str, listing_id: int) -> RentalDetails:
    """Parse a property detail page into a RentalDetails."""
    soup = BeautifulSoup(html, "html.parser")

    h1 = soup.find("h1")
    if h1 is None:
        raise RuntimeError(
            f"Unexpected Surf or Sound response shape: no <h1> on detail page for {listing_id}"
        )
    raw_title = h1.get_text(strip=True)
    name = re.sub(r"\s*-\s*#\d+$", "", raw_title).strip()

    # The detail page can render the main listing's `__property-features` div AFTER
    # the "You may also like" carousel (which contains other listings using the same
    # CSS class). DOM source order puts the main listing first among matching divs,
    # so `find()` (not `find_all()`) reliably returns it.
    feat = soup.find(
        "div", class_=lambda c: c and "sos-property-card__property-features" in c
    )
    town = ""
    bedrooms: int | None = None
    baths_full: int | None = None
    baths_half: int | None = None

    if feat is not None:
        for p in feat.find_all("p", class_="mb-0"):
            label_span = p.find("span", class_=lambda c: c and "sos-letter-spc-1" in c)
            val_span = p.find("span", class_=lambda c: c and "fw-bold" in c)
            if not label_span or not val_span:
                continue
            label = label_span.get_text(strip=True).upper()
            val = val_span.get_text(strip=True)
            if label == "VILLAGE":
                town = val.lower().replace(" ", "-")
            elif label == "BED":
                m = _INT_RE.match(val)
                bedrooms = int(m.group(1)) if m else None
            elif label == "BATH":
                baths_full, baths_half = _parse_baths(val)

    desc_div = soup.find("div", id="property-description")
    description = _strip_html(str(desc_div)) if desc_div else ""

    # Real markup uses <ul class="sos-column-list-3">, not <div>; don't constrain to div.
    amenities_div = soup.find(class_=lambda c: c and "sos-column-list-3" in c)
    amenities: list[str] = []
    seen_amenities: set[str] = set()
    if amenities_div is not None:
        for item in amenities_div.find_all(["li", "p"]):
            txt = item.get_text(strip=True)
            if txt and len(txt) < 200 and txt not in seen_amenities:
                seen_amenities.add(txt)
                amenities.append(txt)

    seen: set[str] = set()
    image_urls: list[str] = []
    for img in soup.find_all("img", attrs={"data-lazy": True}):
        src = img.get("data-lazy", "")
        if src and "/media/" in src:
            clean_src = f"{_BASE}{src}" if src.startswith("/") else src
            path_only = re.sub(r"\?.*$", "", clean_src)
            if path_only not in seen:
                seen.add(path_only)
                image_urls.append(clean_src)

    weekly_rate_min: float | None = None
    weekly_rate_max: float | None = None
    for p in soup.find_all("p"):
        txt = p.get_text(strip=True)
        m = _WEEKLY_RANGE_RE.search(txt)
        if m:
            try:
                weekly_rate_min = float(m.group(1).replace(",", ""))
                weekly_rate_max = float(m.group(2).replace(",", ""))
            except ValueError:
                pass
            break

    weekly_availabilities: list[dict[str, Any]] = []
    for script in soup.find_all("script"):
        txt = script.string or ""
        wa_m = _WEEKLY_AVAIL_RE.search(txt)
        if wa_m:
            try:
                raw_list = json.loads(wa_m.group(1))
                for entry in raw_list:
                    weekly_availabilities.append(
                        {
                            "start_date": entry.get("startDate"),
                            "rate": entry.get("rate"),
                            "formatted_rate": entry.get("formattedRate"),
                            "reference_rate": entry.get("referenceRate"),
                            "is_on_special": bool(entry.get("isOnSpecial")),
                        }
                    )
            except (json.JSONDecodeError, TypeError):
                pass
            break

    return RentalDetails(
        listing_id=listing_id,
        url=f"{_DETAIL_URL}/{listing_id}",
        name=name,
        town=town,
        bedrooms=bedrooms,
        bathrooms_full=baths_full,
        bathrooms_half=baths_half,
        sleeps=None,
        description=description,
        amenities=amenities,
        image_urls=image_urls,
        weekly_rate_min=weekly_rate_min,
        weekly_rate_max=weekly_rate_max,
        weekly_availabilities=weekly_availabilities,
    )


def _fetch_html(url: str, params: dict[str, Any] | None = None) -> str:
    r = requests.get(
        url,
        params=params,
        impersonate="chrome124",
        headers={"Accept-Language": "en", "X-Requested-With": "XMLHttpRequest"},
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
    """Fetch active rentals for a given Hatteras Island village.

    Returns {"search_area", "total_returned", "listings"}.

    Each listing includes: listing_id, url, name, bedrooms, bathrooms_full,
    bathrooms_half, town, location, weekly_rate (USD float, for the
    check_in date if provided or the site default otherwise), check_in.

    Pagination: page size is 24. Pages are fetched until max_results is met
    or no more pages remain.

    check_in: optional YYYY-MM-DD date; shifts the weekly_rate displayed on
    the cards to that arrival week (Saturday-to-Saturday). When omitted the
    site defaults to the upcoming Saturday.
    """
    town_slug = town.strip().lower()
    if town_slug not in VILLAGE_SLUGS:
        valid = ", ".join(sorted(VILLAGE_SLUGS))
        raise ValueError(f"Unknown village {town!r}. Valid villages: {valid}")

    params: dict[str, Any] = {"villages": town_slug}
    if min_bedrooms:
        params["minBedrooms"] = min_bedrooms
    if check_in:
        params["checkin"] = check_in

    first_html = _fetch_html(_SEARCH_URL, params=params)
    first_listings, total_found, page_size = _parse_search_page(first_html, check_in)

    seen_ids: set[int] = {li.listing_id for li in first_listings}
    all_listings: list[RentalListing] = list(first_listings)

    if total_found > page_size and len(all_listings) < max_results:
        total_pages = (total_found + page_size - 1) // page_size
        for page in range(2, total_pages + 1):
            if len(all_listings) >= max_results:
                break
            ajax_params: dict[str, Any] = {"villages": town_slug, "page": page}
            if min_bedrooms:
                ajax_params["minBedrooms"] = min_bedrooms
            if check_in:
                ajax_params["checkin"] = check_in
            html = _fetch_html(_AJAX_SEARCH_URL, params=ajax_params)
            page_listings, _, _ = _parse_search_page(html, check_in)
            for li in page_listings:
                if li.listing_id not in seen_ids:
                    seen_ids.add(li.listing_id)
                    all_listings.append(li)

    filtered = [li for li in all_listings if (li.bedrooms or 0) >= min_bedrooms]
    capped = filtered[:max_results]
    return {
        "search_area": f"{town_slug.title()}, Hatteras Island, NC",
        "total_returned": len(capped),
        "listings": [li.to_dict() for li in capped],
    }


def get_rental_details(rental_url_or_id: str | int) -> dict[str, Any]:
    """Fetch full details for a single Surf or Sound property.

    Accepts a numeric property ID (e.g. 553 or "553") or a canonical URL
    (e.g. "https://www.surforsound.com/hatteras-vacation-rental/property/553").

    Returns {listing_id, url, name, town, bedrooms, bathrooms_full,
    bathrooms_half, sleeps (always None — not surfaced by the site),
    description, amenities, image_urls, weekly_rate_min, weekly_rate_max,
    weekly_availabilities}.

    weekly_availabilities is a list of {start_date, rate, formatted_rate,
    reference_rate, is_on_special} from the embedded JS array.
    """
    prop_id = _coerce_id(rental_url_or_id)
    html = _fetch_html(f"{_DETAIL_URL}/{prop_id}")
    return _parse_detail_page(html, prop_id).to_dict()
