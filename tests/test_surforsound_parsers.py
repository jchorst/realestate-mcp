"""Tests for Surf or Sound HTML parsers with hand-crafted minimal fixtures."""

from __future__ import annotations

import pytest

from realestate_mcp.servers.surforsound import _client

# ---------- minimal HTML fixture builders ----------

_BASE = "https://www.surforsound.com"


def _card_html(
    *,
    prop_id: int = 553,
    name: str = "Splash Mansion",
    village: str = "Salvo",
    bedrooms: int = 8,
    bath_text: str = "8 Full, 2 Half",
    location: str = "Oceanfront",
    price: str = "$4,995 /week",
    checkin: str = "2026-07-04",
    checkout: str = "2026-07-11",
) -> str:
    """Mirror the live Surf or Sound search-result card layout.

    Live markup notes:
      - __details > p.mb-0 contains Bed, Bath, Location only — NOT Village.
      - Village is in a separate sibling div.justify-content-around with text
        like "Village: Avon".
    """
    prop_url = f"{_BASE}/hatteras-vacation-rental/property/{prop_id}?Checkin={checkin}&Checkout={checkout}"  # noqa: E501
    name_cls = "lead sos-property-card_name sos-font_merri text-primary text-center d-inline-block w-100 text-decoration-none m-0"  # noqa: E501
    details_cls = "sos-property-card__details w-100 d-flex flex-column justify-content-between pb-3 px-2"  # noqa: E501
    return f"""
<div class="sos-property-card sos-property-card--small sos-lazy-item d-flex flex-column"
     data-property-url="{prop_url}"
     data-gmap="">
  <div class="card d-block w-100">
    <div class="{name_cls}">
      {name} - #{prop_id}
    </div>
    <div class="{details_cls}">
      <div class="px-2">
        <div class="w-100 d-flex justify-content-between text-center pb-2">
          <p class="mb-0">
            <span class="sos-letter-spc-1 text-uppercase">Bed</span>
            <span class="text-primary fw-bold small text-nowrap">{bedrooms}</span>
          </p>
          <p class="mb-0">
            <span class="sos-letter-spc-1 text-uppercase">Bath</span>
            <span class="text-primary fw-bold small text-nowrap">{bath_text}</span>
          </p>
          <p class="mb-0">
            <span class="sos-letter-spc-1 text-uppercase">Location</span>
            <span class="text-primary fw-bold small text-nowrap">{location}</span>
          </p>
        </div>
        <div class="w-100 d-flex justify-content-center text-center">
          <span class="text-info fw-bold lead text-decoration-none">{price}</span>
        </div>
      </div>
    </div>
    <div class="d-flex justify-content-around text-center py-2">
      <small class="text-primary">Village: {village}</small>
      <small class="text-primary">Saturday Check in</small>
    </div>
  </div>
</div>
"""


def _search_page_html(cards_html: str, total_found: int = 15, page_size: int = 24) -> str:
    return f"""
<!doctype html><html><body>
<div class="row sos-search-results-grid"
     current-page="1"
     total-properties-shown="{min(total_found, page_size)}"
     total-properties-found="{total_found}"
     page-size="{page_size}">
  <div class="row justify-content-center sos-search-grid-pages">
    {cards_html}
  </div>
</div>
</body></html>
"""


def _detail_page_html(
    *,
    prop_id: int = 553,
    name: str = "Splash Mansion",
    village: str = "Salvo",
    bedrooms: int = 8,
    bath_text: str = "8 Full, 2 Half",
    location: str = "Oceanfront",
    description: str = "A wonderful oceanfront home.",
    amenities: list[str] | None = None,
    weekly_min: str = "2,995",
    weekly_max: str = "14,495",
    image_paths: list[str] | None = None,
    weekly_avail_json: str = "[]",
) -> str:
    if amenities is None:
        amenities = ["Private Pool", "Hot Tub", "Elevator"]
    if image_paths is None:
        image_paths = [
            f"/media/abc123/surf-or-sound-{prop_id}-main.jpg?width=800&height=540",
            f"/media/def456/surf-or-sound-{prop_id}-room1.jpg?width=800&height=540",
        ]

    amenity_items = "\n".join(f"<li>{a}</li>" for a in amenities)
    image_tags = "\n".join(
        f'<div class="sos-gallery__nav-slide"><img class="img-fluid" data-lazy="{p}" /></div>'
        for p in image_paths
    )

    return f"""
<!doctype html><html><body>
<script>
window.Sos = window.Sos || {{}};
window.Sos.Property = window.Sos.Property || {{}};
window.Sos.Property.WeeklyAvailabilities = {weekly_avail_json};
</script>
<h1>{name} - #{prop_id}</h1>
<div class="sos-property-card__property-features w-100 d-flex">
  <p class="mb-0">
    <small><span class="small sos-letter-spc-1">VILLAGE</span></small><br/>
    <span class="text-primary fw-bold"> {village} </span>
  </p>
  <p class="mb-0">
    <small><span class="small sos-letter-spc-1">BED</span></small><br/>
    <span class="text-primary fw-bold"> {bedrooms}</span>
  </p>
  <p class="mb-0">
    <small><span class="small sos-letter-spc-1">BATH</span></small><br/>
    <span class="text-primary fw-bold"> {bath_text}</span>
  </p>
  <p class="mb-0">
    <small><span class="small sos-letter-spc-1">LOCATION</span></small><br/>
    <span class="text-primary fw-bold"> {location} </span>
  </p>
</div>
<div id="property-description">
  <p class="text-primary">{description}</p>
</div>
<section class="container sos-property-amenities-container">
  <ul class="sos-column-list-3">
    {amenity_items}
  </ul>
</section>
<p class="text-primary mb-0 opacity-75">Weekly: ${weekly_min} - ${weekly_max}</p>
{image_tags}
</body></html>
"""


# ---------- _parse_search_page ----------


def test_parse_search_page_basic():
    html = _search_page_html(_card_html())
    listings, total_found, page_size = _client._parse_search_page(html, "2026-07-04")
    assert len(listings) == 1
    li = listings[0]
    assert li.listing_id == 553
    assert li.name == "Splash Mansion"
    assert li.bedrooms == 8
    assert li.bathrooms_full == 8
    assert li.bathrooms_half == 2
    assert li.town == "salvo"
    assert li.location == "Oceanfront"
    assert li.weekly_rate == 4995.0
    assert li.check_in == "2026-07-04"
    assert "surforsound.com" in li.url
    assert "?" not in li.url
    assert total_found == 15
    assert page_size == 24


def test_parse_search_page_multiple_cards():
    cards = "".join(
        _card_html(prop_id=i + 100, name=f"House {i}", bedrooms=i + 3) for i in range(5)
    )
    html = _search_page_html(cards, total_found=5)
    listings, total_found, _ = _client._parse_search_page(html, "")
    assert len(listings) == 5
    assert total_found == 5
    ids = {li.listing_id for li in listings}
    assert ids == {100, 101, 102, 103, 104}


def test_parse_search_page_no_price():
    html = _search_page_html(_card_html(price="Contact us"))
    listings, _, _ = _client._parse_search_page(html, "")
    assert listings[0].weekly_rate is None


def test_parse_search_page_skips_card_without_id():
    bad_card = """<div class="sos-property-card" data-property-url="/no-property-id-here"></div>"""
    html = _search_page_html(bad_card + _card_html(prop_id=999))
    listings, _, _ = _client._parse_search_page(html, "")
    assert len(listings) == 1
    assert listings[0].listing_id == 999


def test_parse_search_page_ajax_fragment_no_grid_attrs():
    prop_url = f"{_BASE}/hatteras-vacation-rental/property/727?Checkin=2026-05-16&Checkout=2026-05-23"  # noqa: E501
    name_cls = "lead sos-property-card_name sos-font_merri text-primary text-center d-inline-block w-100 text-decoration-none m-0"  # noqa: E501
    details_cls = "sos-property-card__details w-100 d-flex flex-column justify-content-between pb-3 px-2"  # noqa: E501
    fragment_html = f"""
<div class="sos-property-card sos-property-card--small sos-lazy-item d-flex flex-column"
     data-property-url="{prop_url}">
  <div class="card d-block w-100">
    <div class="{name_cls}">
      Knights In Salvo - #727
    </div>
    <div class="{details_cls}">
      <div class="px-2">
        <div class="w-100 d-flex justify-content-between text-center pb-2">
          <p class="mb-0">
            <span class="sos-letter-spc-1 text-uppercase">Bed</span>
            <span class="text-primary fw-bold small text-nowrap">4</span>
          </p>
          <p class="mb-0">
            <span class="sos-letter-spc-1 text-uppercase">Bath</span>
            <span class="text-primary fw-bold small text-nowrap">3 Full, 1 Half</span>
          </p>
          <p class="mb-0">
            <span class="sos-letter-spc-1 text-uppercase">Location</span>
            <span class="text-primary fw-bold small text-nowrap">Oceanside</span>
          </p>
        </div>
        <div class="w-100 d-flex justify-content-center text-center">
          <span class="text-info fw-bold lead text-decoration-none">$2,995 /week</span>
        </div>
      </div>
    </div>
  </div>
</div>
"""
    listings, total_found, _page_size = _client._parse_search_page(fragment_html, "2026-05-16")
    assert len(listings) == 1
    assert listings[0].listing_id == 727
    assert listings[0].bedrooms == 4
    assert listings[0].weekly_rate == 2995.0
    assert total_found == 0


def test_parse_search_page_raises_on_empty_with_no_grid():
    with pytest.raises(RuntimeError, match="Unexpected Surf or Sound response shape"):
        _client._parse_search_page("<html><body><p>Nothing here</p></body></html>", "")


def test_parse_search_page_empty_grid_ok():
    html = _search_page_html("", total_found=0)
    listings, total_found, _ = _client._parse_search_page(html, "")
    assert listings == []
    assert total_found == 0


# ---------- _parse_detail_page ----------


def test_parse_detail_page_basic():
    html = _detail_page_html()
    d = _client._parse_detail_page(html, 553)
    assert d.listing_id == 553
    assert d.name == "Splash Mansion"
    assert d.town == "salvo"
    assert d.bedrooms == 8
    assert d.bathrooms_full == 8
    assert d.bathrooms_half == 2
    assert d.weekly_rate_min == 2995.0
    assert d.weekly_rate_max == 14495.0
    assert "wonderful" in d.description.lower()
    assert "surforsound.com" in d.url


def test_parse_detail_page_amenities():
    html = _detail_page_html(amenities=["Private Pool", "Hot Tub", "Pets Allowed"])
    d = _client._parse_detail_page(html, 553)
    assert "Private Pool" in d.amenities
    assert "Hot Tub" in d.amenities
    assert "Pets Allowed" in d.amenities


def test_parse_detail_page_image_urls():
    html = _detail_page_html(
        image_paths=[
            "/media/abc/surf-or-sound-553-main.jpg?width=800&height=540",
            "/media/def/surf-or-sound-553-room1.jpg?width=800&height=540",
        ]
    )
    d = _client._parse_detail_page(html, 553)
    assert len(d.image_urls) == 2
    assert all("surforsound.com" in url for url in d.image_urls)
    assert all("/media/" in url for url in d.image_urls)


def test_parse_detail_page_image_deduplication():
    same_path = "/media/abc/surf-or-sound-553-main.jpg?width=800&height=540"
    html = _detail_page_html(image_paths=[same_path, same_path])
    d = _client._parse_detail_page(html, 553)
    assert len(d.image_urls) == 1


def test_parse_detail_page_weekly_availabilities():
    avail_json = (
        '[{"isOnSpecial":false,"startDate":"2026-07-04","rate":14495.11,'
        '"formattedRate":"$14,495","referenceRate":13995.0,'
        '"formattedReferenceRate":"$13,995","type":4}]'
    )
    html = _detail_page_html(weekly_avail_json=avail_json)
    d = _client._parse_detail_page(html, 553)
    assert len(d.weekly_availabilities) == 1
    wa = d.weekly_availabilities[0]
    assert wa["start_date"] == "2026-07-04"
    assert wa["rate"] == 14495.11
    assert wa["formatted_rate"] == "$14,495"
    assert wa["is_on_special"] is False


def test_parse_detail_page_no_weekly_availabilities():
    html = _detail_page_html(weekly_avail_json="[]")
    d = _client._parse_detail_page(html, 553)
    assert d.weekly_availabilities == []


def test_parse_detail_page_sleeps_is_none():
    html = _detail_page_html()
    d = _client._parse_detail_page(html, 553)
    assert d.sleeps is None


def test_parse_detail_page_strips_you_may_also_like_stats():
    # Build a page where the main property has 8 beds and a 'you may also like'
    # section references properties with different bed counts.
    also_like_section = """
<h2 class="text-center sos-font_merri">You may also like</h2>
<div class="sos-property-card__property-features w-100 d-flex">
  <p class="mb-0">
    <small><span class="small sos-letter-spc-1">VILLAGE</span></small><br/>
    <span class="text-primary fw-bold">Avon</span>
  </p>
  <p class="mb-0">
    <small><span class="small sos-letter-spc-1">BED</span></small><br/>
    <span class="text-primary fw-bold">3</span>
  </p>
  <p class="mb-0">
    <small><span class="small sos-letter-spc-1">BATH</span></small><br/>
    <span class="text-primary fw-bold">2 Full, 1 Half</span>
  </p>
</div>
"""
    main_html = _detail_page_html(bedrooms=8, bath_text="8 Full, 2 Half")
    full_html = main_html.replace("</body>", also_like_section + "</body>")
    d = _client._parse_detail_page(full_html, 553)
    assert d.bedrooms == 8
    assert d.bathrooms_full == 8


def test_parse_detail_page_raises_on_missing_h1():
    with pytest.raises(RuntimeError, match="Unexpected Surf or Sound response shape"):
        _client._parse_detail_page("<html><body><p>No h1 here</p></body></html>", 553)
