"""End-to-end integration tests for the Surf or Sound client with mocked HTTP."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from realestate_mcp.servers.surforsound import _client, server

_BASE = "https://www.surforsound.com"


def _fake_response(html: str = "", status: int = 200) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.raise_for_status = MagicMock()
    r.text = html
    return r


def _card_html(
    prop_id: int,
    name: str = "",
    bedrooms: int = 4,
    village: str = "avon",
    bath_text: str = "3 Full",
    price: str = "$2,995 /week",
    checkin: str = "2026-07-04",
    checkout: str = "2026-07-11",
) -> str:
    display_name = name or f"House {prop_id}"
    prop_url = f"{_BASE}/hatteras-vacation-rental/property/{prop_id}?Checkin={checkin}&Checkout={checkout}"  # noqa: E501
    details_cls = "sos-property-card__details w-100 d-flex flex-column justify-content-between pb-3 px-2"  # noqa: E501
    return f"""
<div class="sos-property-card sos-property-card--small"
     data-property-url="{prop_url}">
  <div class="card d-block w-100">
    <div class="lead sos-property-card_name sos-font_merri text-primary">
      {display_name} - #{prop_id}
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
            <span class="sos-letter-spc-1 text-uppercase">Village</span>
            <span class="text-primary fw-bold small text-nowrap">{village.title()}</span>
          </p>
          <p class="mb-0">
            <span class="sos-letter-spc-1 text-uppercase">Location</span>
            <span class="text-primary fw-bold small text-nowrap">Oceanfront</span>
          </p>
        </div>
        <div class="w-100 d-flex justify-content-center text-center">
          <span class="text-info fw-bold lead text-decoration-none">{price}</span>
        </div>
      </div>
    </div>
  </div>
</div>
"""


def _full_page_html(cards_html: str, total_found: int = 5, page_size: int = 24) -> str:
    return f"""
<!doctype html><html><body>
<div class="row sos-search-results-grid"
     current-page="1"
     total-properties-shown="{min(total_found, page_size)}"
     total-properties-found="{total_found}"
     page-size="{page_size}">
  <div class="row sos-search-grid-pages">
    {cards_html}
  </div>
</div>
</body></html>
"""


def _detail_html(
    prop_id: int = 553,
    name: str = "Splash Mansion",
    village: str = "Salvo",
    bedrooms: int = 8,
    bath_text: str = "8 Full, 2 Half",
) -> str:
    return f"""
<!doctype html><html><body>
<script>
window.Sos = window.Sos || {{}};
window.Sos.Property = window.Sos.Property || {{}};
window.Sos.Property.WeeklyAvailabilities = [{{"isOnSpecial":false,
"startDate":"2026-07-04","rate":14495.11,"formattedRate":"$14,495",
"referenceRate":13995.0,"formattedReferenceRate":"$13,995","type":4}}];
</script>
<h1>{name} - #{prop_id}</h1>
<div class="sos-property-card__property-features w-100">
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
    <span class="text-primary fw-bold"> Oceanfront </span>
  </p>
</div>
<div id="property-description"><p>A great vacation home.</p></div>
<div class="sos-column-list-3"><p>Private Pool</p><p>Hot Tub</p></div>
<p class="text-primary mb-0 opacity-75">Weekly: $2,995 - $14,495</p>
<div class="sos-gallery__nav-slide">
  <img class="img-fluid" data-lazy="/media/abc/surf-or-sound-{prop_id}-main.jpg" />
</div>
</body></html>
"""


# ---------- search_rentals ----------


def test_search_rentals_returns_listings(monkeypatch):
    cards = "".join(_card_html(i + 100, bedrooms=4) for i in range(5))
    html = _full_page_html(cards, total_found=5)
    monkeypatch.setattr(_client.requests, "get", lambda *a, **kw: _fake_response(html))

    result = _client.search_rentals("avon")
    assert result["total_returned"] == 5
    ids = {li["listing_id"] for li in result["listings"]}
    assert ids == {100, 101, 102, 103, 104}


def test_search_rentals_min_bedrooms_filter_client_side(monkeypatch):
    cards = "".join(
        _card_html(i, bedrooms=i + 2) for i in range(1, 5)
    )
    html = _full_page_html(cards, total_found=4)
    monkeypatch.setattr(_client.requests, "get", lambda *a, **kw: _fake_response(html))

    result = _client.search_rentals("avon", min_bedrooms=4)
    returned_beds = [li["bedrooms"] for li in result["listings"]]
    assert all(b >= 4 for b in returned_beds)


def test_search_rentals_max_results_cap(monkeypatch):
    cards = "".join(_card_html(i) for i in range(1, 20))
    html = _full_page_html(cards, total_found=19)
    monkeypatch.setattr(_client.requests, "get", lambda *a, **kw: _fake_response(html))

    result = _client.search_rentals("avon", max_results=7)
    assert result["total_returned"] == 7
    assert len(result["listings"]) == 7


def test_search_rentals_includes_search_area(monkeypatch):
    html = _full_page_html("", total_found=0)
    monkeypatch.setattr(_client.requests, "get", lambda *a, **kw: _fake_response(html))

    result = _client.search_rentals("avon")
    assert "Avon" in result["search_area"]
    assert "Hatteras" in result["search_area"]


def test_search_rentals_raises_on_unknown_village():
    with pytest.raises(ValueError, match="Unknown village"):
        _client.search_rentals("corolla")


def test_search_rentals_raises_on_schema_drift(monkeypatch):
    monkeypatch.setattr(
        _client.requests,
        "get",
        lambda *a, **kw: _fake_response("<html><body><p>nothing</p></body></html>"),
    )
    with pytest.raises(RuntimeError, match="Unexpected Surf or Sound response shape"):
        _client.search_rentals("avon")


def test_search_rentals_check_in_passed_to_url(monkeypatch):
    captured_params = []

    def fake_get(url, params=None, **kw):
        captured_params.append(params or {})
        html = _full_page_html("", total_found=0)
        return _fake_response(html)

    monkeypatch.setattr(_client.requests, "get", fake_get)

    _client.search_rentals("avon", check_in="2026-07-04")
    assert captured_params[0].get("checkin") == "2026-07-04"


def test_search_rentals_min_bedrooms_passed_to_url(monkeypatch):
    captured_params = []

    def fake_get(url, params=None, **kw):
        captured_params.append(params or {})
        html = _full_page_html("", total_found=0)
        return _fake_response(html)

    monkeypatch.setattr(_client.requests, "get", fake_get)

    _client.search_rentals("salvo", min_bedrooms=6)
    assert captured_params[0].get("minBedrooms") == 6


def test_search_rentals_pagination_fetches_second_page(monkeypatch):
    page1_cards = "".join(_card_html(i + 1) for i in range(24))
    page1_html = _full_page_html(page1_cards, total_found=30, page_size=24)

    page2_cards = "".join(_card_html(i + 25) for i in range(6))

    call_count = [0]

    def fake_get(url, params=None, **kw):
        call_count[0] += 1
        if "umbraco" in url:
            return _fake_response(page2_cards)
        return _fake_response(page1_html)

    monkeypatch.setattr(_client.requests, "get", fake_get)

    result = _client.search_rentals("rodanthe", max_results=50)
    assert call_count[0] == 2
    assert result["total_returned"] == 30


def test_search_rentals_no_second_page_when_all_fit(monkeypatch):
    cards = "".join(_card_html(i + 1) for i in range(10))
    html = _full_page_html(cards, total_found=10, page_size=24)
    call_count = [0]

    def fake_get(url, **kw):
        call_count[0] += 1
        return _fake_response(html)

    monkeypatch.setattr(_client.requests, "get", fake_get)

    result = _client.search_rentals("avon")
    assert call_count[0] == 1
    assert result["total_returned"] == 10


def test_search_rentals_deduplicates_across_pages(monkeypatch):
    overlap_id = 99
    page1_cards = "".join(_card_html(i + 1) for i in range(24))
    overlap_card = _card_html(overlap_id)
    page1_html = _full_page_html(page1_cards + overlap_card, total_found=30, page_size=24)
    page2_with_overlap = overlap_card + "".join(_card_html(i + 200) for i in range(5))

    def fake_get(url, params=None, **kw):
        if "umbraco" in url:
            return _fake_response(page2_with_overlap)
        return _fake_response(page1_html)

    monkeypatch.setattr(_client.requests, "get", fake_get)

    result = _client.search_rentals("avon", max_results=100)
    all_ids = [li["listing_id"] for li in result["listings"]]
    assert all_ids.count(overlap_id) == 1


# ---------- get_rental_details ----------


def test_get_rental_details_by_numeric_id(monkeypatch):
    monkeypatch.setattr(
        _client.requests, "get", lambda *a, **kw: _fake_response(_detail_html(553))
    )
    d = _client.get_rental_details("553")
    assert d["listing_id"] == 553
    assert d["bedrooms"] == 8
    assert d["bathrooms_full"] == 8
    assert d["bathrooms_half"] == 2
    assert d["weekly_rate_min"] == 2995.0
    assert d["weekly_rate_max"] == 14495.0


def test_get_rental_details_by_bare_int(monkeypatch):
    monkeypatch.setattr(
        _client.requests, "get", lambda *a, **kw: _fake_response(_detail_html(553))
    )
    d = _client.get_rental_details(553)
    assert d["listing_id"] == 553


def test_get_rental_details_by_url(monkeypatch):
    captured_urls = []

    def fake_get(url, **kw):
        captured_urls.append(url)
        return _fake_response(_detail_html(553))

    monkeypatch.setattr(_client.requests, "get", fake_get)

    d = _client.get_rental_details(
        "https://www.surforsound.com/hatteras-vacation-rental/property/553"
    )
    assert d["listing_id"] == 553
    assert "553" in captured_urls[0]


def test_get_rental_details_amenities(monkeypatch):
    monkeypatch.setattr(
        _client.requests, "get", lambda *a, **kw: _fake_response(_detail_html(553))
    )
    d = _client.get_rental_details("553")
    assert "Private Pool" in d["amenities"]
    assert "Hot Tub" in d["amenities"]


def test_get_rental_details_weekly_availabilities(monkeypatch):
    monkeypatch.setattr(
        _client.requests, "get", lambda *a, **kw: _fake_response(_detail_html(553))
    )
    d = _client.get_rental_details("553")
    assert len(d["weekly_availabilities"]) == 1
    wa = d["weekly_availabilities"][0]
    assert wa["start_date"] == "2026-07-04"
    assert wa["rate"] == 14495.11


def test_get_rental_details_sleeps_is_none(monkeypatch):
    monkeypatch.setattr(
        _client.requests, "get", lambda *a, **kw: _fake_response(_detail_html(553))
    )
    d = _client.get_rental_details("553")
    assert d["sleeps"] is None


def test_get_rental_details_image_urls(monkeypatch):
    monkeypatch.setattr(
        _client.requests, "get", lambda *a, **kw: _fake_response(_detail_html(553))
    )
    d = _client.get_rental_details("553")
    assert len(d["image_urls"]) >= 1
    assert all("surforsound.com" in url for url in d["image_urls"])


def test_get_rental_details_raises_on_schema_drift(monkeypatch):
    monkeypatch.setattr(
        _client.requests,
        "get",
        lambda *a, **kw: _fake_response("<html><body><p>nothing</p></body></html>"),
    )
    with pytest.raises(RuntimeError, match="Unexpected Surf or Sound response shape"):
        _client.get_rental_details("553")


# ---------- MCP server tools ----------


def test_mcp_search_rentals_tool(monkeypatch):
    cards = "".join(_card_html(i + 10, bedrooms=i + 3) for i in range(3))
    html = _full_page_html(cards, total_found=3)
    monkeypatch.setattr(_client.requests, "get", lambda *a, **kw: _fake_response(html))

    result = asyncio.run(server.search_rentals(town="avon", min_bedrooms=4))
    for li in result["listings"]:
        assert li["bedrooms"] >= 4


def test_mcp_get_rental_details_tool(monkeypatch):
    monkeypatch.setattr(
        _client.requests, "get", lambda *a, **kw: _fake_response(_detail_html(777))
    )
    result = asyncio.run(server.get_rental_details("777"))
    assert result["listing_id"] == 777
