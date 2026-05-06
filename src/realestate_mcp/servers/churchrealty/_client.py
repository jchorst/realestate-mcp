"""Minimal Church Realty search client.

Church Realty (churchrealty.com) is a niche real-estate firm specializing in
church and religious-use properties. **Inventory is Texas-only** — exclusively
DFW and Houston metro listings. Do not query for properties outside Texas; the
site does not carry them.

Strategy: the /properties/ index returns a single server-rendered HTML page
(~272 KB) listing all ~20-30 active properties. No pagination, no public JSON
API, no URL-exposed filter parameters. Filtering is applied client-side after
fetching the full index.

Detail pages (GET /property/<slug>/) are also server-rendered HTML; all data
including price, address, building stats, and gallery images render in the
static DOM.

Schema-drift breadcrumbs (selectors this client depends on):
  Index (/properties/):
    - div.property_wrap              — one per listing card (22 cards as of 2026-05)
    - div.featured_image > img[0]    — listing preview image (first img, before div.sri-listing)
    - div.col_content > p            — [0] street, [1] "City, ST ZIP", [2] "Agent : Name",
                                       [3] "Phone : NNN-NNN-NNNN"
    - p.prop_button > a[href]        — canonical detail URL (slug = last path segment)

  Detail (/property/<slug>/):
    - div.property_wrap              — main wrapper (one on page)
    - div.property_top_area > h1     — listing name/headline
    - div.property_item_content > h3 — brief description (optional, varies per listing)
    - div.property_item_content > p  — data lines: address, "Land Area: X acres",
                                       "Price: $X", "Building: X sqft", "Seating: X",
                                       "Parking: X", "Agent : Name", "Phone: ...",
                                       "Email: ..."
    - div.property_gallery_images > img[src] — gallery images (deduplicate; slider
                                               doubles each img in the DOM)

listing_type is derived from the URL slug:
  - slug contains "for-sale"  -> "For Sale"
  - slug contains "for-lease" -> "For Lease"
  - otherwise                 -> "Unknown"

Price: rendered as "Price: $3,900,000" or "Price: Please call agent for price".
The latter produces price=None (not a RuntimeError — it is an expected variant).

agent_name / agent_phone: parsed from "Agent : Name" / "Phone: NNN" paragraphs.
They vary by listing and may be None if the paragraph is absent.

building_sqft: integer parsed from "Building: 51,325 sqft" — handles "~" and
trailing text like "plus 3,000 sqft of portable bldgs".

lot_acres: float parsed from "Land Area: 4.52 acres".

year_built: not present anywhere in the site's HTML. Always None.
"""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from typing import Any

from bs4 import BeautifulSoup
from curl_cffi import requests

_BASE = "https://www.churchrealty.com"
_INDEX_URL = f"{_BASE}/properties/"
_DETAIL_BASE = f"{_BASE}/property"

CHURCHREALTY_PROXY = os.environ.get("CHURCHREALTY_PROXY_URL", "")

_PRICE_RE = re.compile(r"\$([\d,]+(?:\.\d+)?)")
_INT_RE = re.compile(r"(\d[\d,]*)")
_FLOAT_RE = re.compile(r"([\d,]+(?:\.\d+)?)")
_ADDR_RE = re.compile(r"^(.+),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)$")


@dataclass
class PropertyCard:
    listing_id: str
    url: str
    name: str
    address: str
    city: str
    state: str
    zip: str
    price: float | None
    listing_type: str
    image_url: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PropertyDetails:
    listing_id: str
    url: str
    name: str
    address: str
    city: str
    state: str
    zip: str
    price: float | None
    listing_type: str
    description: str | None
    building_sqft: int | None
    lot_acres: float | None
    year_built: int | None
    image_urls: list[str]
    agent_name: str | None
    agent_phone: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _proxies() -> dict[str, str] | None:
    return {"http": CHURCHREALTY_PROXY, "https": CHURCHREALTY_PROXY} if CHURCHREALTY_PROXY else None


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


def _slug_from_url(url: str) -> str:
    return url.rstrip("/").split("/")[-1]


def _listing_type_from_slug(slug: str) -> str:
    if "for-lease" in slug:
        return "For Lease"
    if "for-sale" in slug:
        return "For Sale"
    return "Unknown"


def _parse_price(text: str | None) -> float | None:
    if not text:
        return None
    m = _PRICE_RE.search(text)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _parse_int(text: str | None) -> int | None:
    if not text:
        return None
    m = _INT_RE.search(text)
    if not m:
        return None
    try:
        return int(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _parse_float(text: str | None) -> float | None:
    if not text:
        return None
    m = _FLOAT_RE.search(text)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _parse_address_line2(line2: str) -> tuple[str, str, str]:
    """Parse 'City, ST ZIP' into (city, state, zip). Returns ('', '', '') on failure."""
    m = _ADDR_RE.match(line2.strip())
    if m:
        return m.group(1).strip(), m.group(2), m.group(3)
    return "", "", ""


def _coerce_id(listing_url_or_slug: str | int) -> str:
    """Normalise a listing reference to its URL slug.

    Accepts:
    - A bare int (converted to string — valid if the slug is purely numeric, but
      Church Realty slugs are text strings; this path exists to satisfy the
      str|int type contract and tests).
    - A plain slug string: "church-property-for-sale-houston-tx-10355-mills-road"
    - A full detail URL: "https://www.churchrealty.com/property/<slug>/"
    """
    if isinstance(listing_url_or_slug, int):
        return str(listing_url_or_slug)
    stripped = listing_url_or_slug.strip().rstrip("/")
    if "/property/" in stripped:
        return stripped.split("/property/")[-1]
    return stripped


def _parse_index_page(html: str) -> list[PropertyCard]:
    """Parse the /properties/ index page into a list of PropertyCard objects."""
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.find_all("div", class_="property_wrap")
    if not cards:
        raise RuntimeError(
            "Unexpected Church Realty response shape: "
            "no div.property_wrap cards found on the properties index page"
        )

    results: list[PropertyCard] = []
    for card in cards:
        link_tag = card.find("a", href=re.compile(r"/property/"))
        if not link_tag:
            continue
        detail_url = link_tag["href"].rstrip("/") + "/"
        slug = _slug_from_url(detail_url)

        col_content = card.find("div", class_="col_content")
        paras = col_content.find_all("p") if col_content else []
        para_texts = [p.get_text(strip=True) for p in paras]

        street = para_texts[0] if len(para_texts) > 0 else ""
        city, state, zip_ = (
            _parse_address_line2(para_texts[1]) if len(para_texts) > 1 else ("", "", "")
        )

        # The theme embeds a branded logo thumbnail inside div.sri-listing on every
        # card; skipping those leaves the real listing photo as the first remaining img.
        feat_div = card.find("div", class_="featured_image")
        image_url: str | None = None
        if feat_div:
            sri = feat_div.find("div", class_="sri-listing")
            sri_imgs = set(sri.find_all("img")) if sri else set()
            for img in feat_div.find_all("img"):
                if img in sri_imgs:
                    continue
                src = img.get("src", "")
                if src:
                    image_url = src
                    break

        results.append(
            PropertyCard(
                listing_id=slug,
                url=detail_url,
                name=street,
                address=street,
                city=city,
                state=state,
                zip=zip_,
                price=None,
                listing_type=_listing_type_from_slug(slug),
                image_url=image_url,
            )
        )

    return results


def _parse_detail_page(html: str, slug: str) -> PropertyDetails:
    """Parse a /property/<slug>/ detail page into a PropertyDetails object."""
    soup = BeautifulSoup(html, "html.parser")

    wrap = soup.find("div", class_="property_wrap")
    if wrap is None:
        raise RuntimeError(
            f"Unexpected Church Realty response shape: "
            f"no div.property_wrap on detail page for {slug!r}"
        )

    top_area = wrap.find("div", class_="property_top_area")
    h1 = top_area.find("h1") if top_area else wrap.find("h1")
    name = h1.get_text(strip=True) if h1 else ""

    item_content = wrap.find("div", class_="property_item_content")
    if item_content is None:
        raise RuntimeError(
            f"Unexpected Church Realty response shape: "
            f"no div.property_item_content on detail page for {slug!r}"
        )

    h3 = item_content.find("h3")
    description = h3.get_text(strip=True) if h3 else None

    street = ""
    city = ""
    state = ""
    zip_ = ""
    price: float | None = None
    building_sqft: int | None = None
    lot_acres: float | None = None
    agent_name: str | None = None
    agent_phone: str | None = None

    # Known prefixes we recognise but don't surface as fields (Seating, Parking).
    # Listing them explicitly stops them from being captured as the street/city
    # fallthrough below if they happen to appear before the address paragraph.
    _ignored_prefixes = ("seating:", "parking:")

    for p in item_content.find_all("p"):
        txt = p.get_text(strip=True)
        tl = txt.lower()
        if tl.startswith("price:"):
            price = _parse_price(txt)
        elif tl.startswith("building:"):
            building_sqft = _parse_int(re.sub(r"(?i)^building:\s*", "", txt))
        elif tl.startswith("land area:"):
            lot_acres = _parse_float(re.sub(r"(?i)^land area:\s*", "", txt))
        elif tl.startswith("agent"):
            agent_name = re.sub(r"(?i)^agent\s*:\s*", "", txt).strip()
        elif tl.startswith("phone"):
            raw = re.sub(r"(?i)^phone:?\s*", "", p.get_text(separator=" ", strip=True)).strip()
            agent_phone = raw if raw else None
        elif tl.startswith(_ignored_prefixes):
            continue
        elif not street and not city:
            street = txt
        elif street and not city:
            city, state, zip_ = _parse_address_line2(txt)

    # Gallery images: deduplicate by src (slider duplicates each image in the DOM)
    gallery_div = soup.find("div", class_="property_gallery_images")
    seen_srcs: set[str] = set()
    image_urls: list[str] = []
    if gallery_div:
        for img in gallery_div.find_all("img"):
            src = img.get("src", "")
            if src and src not in seen_srcs:
                seen_srcs.add(src)
                image_urls.append(src)

    detail_url = f"{_DETAIL_BASE}/{slug}/"
    return PropertyDetails(
        listing_id=slug,
        url=detail_url,
        name=name,
        address=street,
        city=city,
        state=state,
        zip=zip_,
        price=price,
        listing_type=_listing_type_from_slug(slug),
        description=description,
        building_sqft=building_sqft,
        lot_acres=lot_acres,
        year_built=None,
        image_urls=image_urls,
        agent_name=agent_name,
        agent_phone=agent_phone,
    )


def search_listings(
    city: str = "",
    state: str = "",
    listing_type: str = "",
    max_results: int = 50,
) -> dict[str, Any]:
    """Fetch all Church Realty listings and apply optional client-side filters.

    NOTE: Church Realty inventory is Texas-only (DFW + Houston metros).
    The /properties/ index returns all active listings (~20-30) on a single page.
    Prices are NOT available on the index page — they are on detail pages only.
    Use get_listing_details() to retrieve prices for specific listings. There
    are no price filter parameters here for that reason.

    Args:
        city: Case-insensitive substring match against the listing's city field.
        state: Case-insensitive substring match against state (e.g. "TX").
        listing_type: Case-insensitive substring match: "sale"/"buy" -> For Sale,
                      "lease"/"rent" -> For Lease. Empty = all types.
        max_results: Maximum number of listings to return.

    Returns:
        {"search_area", "total_returned", "listings"}. Each listing includes:
        listing_id, url, name, address, city, state, zip, price (always None —
        not available on index page), listing_type, image_url.
    """
    html = _fetch_html(_INDEX_URL)
    cards = _parse_index_page(html)

    filtered: list[PropertyCard] = []
    for card in cards:
        if city and city.lower() not in card.city.lower():
            continue
        if state and state.lower() not in card.state.lower():
            continue
        if listing_type:
            lt_lower = listing_type.lower()
            card_lt_lower = card.listing_type.lower()
            if "lease" in lt_lower or "rent" in lt_lower:
                if "lease" not in card_lt_lower:
                    continue
            elif "sale" in lt_lower or "buy" in lt_lower:
                if "sale" not in card_lt_lower:
                    continue
            else:
                if lt_lower not in card_lt_lower:
                    continue
        filtered.append(card)

    capped = filtered[:max_results]
    return {
        "search_area": "Texas (DFW and Houston metros)",
        "total_returned": len(capped),
        "listings": [c.to_dict() for c in capped],
    }


def get_listing_details(listing_url_or_slug: str | int) -> dict[str, Any]:
    """Fetch full details for a single Church Realty property.

    Accepts a slug string, full detail URL, or bare int (converted to string).

    Returns {listing_id, url, name, address, city, state, zip, price,
    listing_type, description, building_sqft, lot_acres, year_built (always
    None — not surfaced by the site), image_urls, agent_name, agent_phone}.

    price is None when the listing reads "Please call agent for price".
    description is the brief headline from the <h3> tag (e.g., "Adjacent to
    the new Humble ISD stadium!"). Some listings omit it.
    agent_phone includes extensions when present (e.g., "281-540-2008 ext 2").
    """
    slug = _coerce_id(listing_url_or_slug)
    html = _fetch_html(f"{_DETAIL_BASE}/{slug}/")
    return _parse_detail_page(html, slug).to_dict()
