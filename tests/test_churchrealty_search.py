"""End-to-end tests for the Church Realty client with mocked HTTP."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from realestate_mcp.servers.churchrealty import _client, server

# ---------- HTTP mock helpers ----------


def _fake_response(html: str, status: int = 200) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.raise_for_status = MagicMock()
    r.text = html
    return r


def _card_html(
    slug: str,
    street: str,
    addr2: str,
    img: str = "https://www.churchrealty.com/wp-content/uploads/img.jpg",
) -> str:
    return f"""
<div class="property_wrap">
  <div class="col1">
    <div class="featured_image">
      <img src="{img}"/>
      <div class="sri-listing"><img src="https://www.churchrealty.com/logo.png"/></div>
    </div>
    <div class="col_content">
      <p>{street}</p>
      <p>{addr2}</p>
      <p>Agent : Test Agent</p>
      <p>Phone : 555-555-5555</p>
    </div>
    <p class="prop_button">
      <a href="https://www.churchrealty.com/property/{slug}/">View Details</a>
    </p>
  </div>
</div>
"""


def _index_html(*cards: str) -> str:
    return "<html><body>" + "".join(cards) + "</body></html>"


def _detail_html(
    slug: str,
    h1: str,
    street: str,
    addr2: str,
    price_line: str = "Price: $1,500,000",
) -> str:
    return f"""
<html><body>
<div class="property_wrap">
  <div class="property_top_area"><h1>{h1}</h1></div>
  <div class="property_item_content">
    <h3>A great church property</h3>
    <p>{street}</p>
    <p>{addr2}</p>
    <p>Land Area: 2.5 acres</p>
    <p>{price_line}</p>
    <p>Building: 8,000 sqft</p>
    <p>Agent : Jane Doe</p>
    <p>Phone: 214-555-9999</p>
    <p>Email: jane@churchrealty.com</p>
  </div>
</div>
<div class="property_gallery_images">
  <img src="https://www.churchrealty.com/wp-content/uploads/a.jpg"/>
  <img src="https://www.churchrealty.com/wp-content/uploads/b.jpg"/>
</div>
</body></html>
"""


# Short slug aliases to keep lines under 100 chars in test calls
_HOUSTON_SALE = "church-property-for-sale-houston-tx-aaa"
_DALLAS_SALE = "church-property-for-sale-dallas-tx-bbb"
_FW_SALE = "church-property-for-sale-fort-worth-tx-ccc"
_ARLINGTON_LEASE = "multi-use-space-for-lease-arlington-tx-bbb"


# ---------- search_listings ----------


def test_search_listings_returns_all_cards(monkeypatch):
    html = _index_html(
        _card_html(_HOUSTON_SALE, "100 Main St", "Houston, TX 77001"),
        _card_html(_DALLAS_SALE, "200 Oak Ave", "Dallas, TX 75201"),
    )
    monkeypatch.setattr(_client.requests, "get", lambda *a, **kw: _fake_response(html))

    result = _client.search_listings()
    assert result["total_returned"] == 2
    assert result["search_area"] == "Texas (DFW and Houston metros)"
    ids = {li["listing_id"] for li in result["listings"]}
    assert _HOUSTON_SALE in ids
    assert _DALLAS_SALE in ids


def test_search_listings_city_filter(monkeypatch):
    html = _index_html(
        _card_html(_HOUSTON_SALE, "100 Main St", "Houston, TX 77001"),
        _card_html(_DALLAS_SALE, "200 Oak Ave", "Dallas, TX 75201"),
        _card_html(_FW_SALE, "300 Elm St", "Fort Worth, TX 76101"),
    )
    monkeypatch.setattr(_client.requests, "get", lambda *a, **kw: _fake_response(html))

    result = _client.search_listings(city="Houston")
    assert result["total_returned"] == 1
    assert result["listings"][0]["city"] == "Houston"


def test_search_listings_state_filter(monkeypatch):
    html = _index_html(
        _card_html(_HOUSTON_SALE, "100 Main St", "Houston, TX 77001"),
        _card_html(_DALLAS_SALE, "200 Oak Ave", "Dallas, TX 75201"),
    )
    monkeypatch.setattr(_client.requests, "get", lambda *a, **kw: _fake_response(html))

    result = _client.search_listings(state="TX")
    assert result["total_returned"] == 2


def test_search_listings_listing_type_sale_filter(monkeypatch):
    html = _index_html(
        _card_html(_HOUSTON_SALE, "100 Main St", "Houston, TX 77001"),
        _card_html(_ARLINGTON_LEASE, "700 Lease Rd", "Arlington, TX 76001"),
    )
    monkeypatch.setattr(_client.requests, "get", lambda *a, **kw: _fake_response(html))

    result = _client.search_listings(listing_type="sale")
    assert result["total_returned"] == 1
    assert result["listings"][0]["listing_type"] == "For Sale"


def test_search_listings_listing_type_lease_filter(monkeypatch):
    html = _index_html(
        _card_html(_HOUSTON_SALE, "100 Main St", "Houston, TX 77001"),
        _card_html(_ARLINGTON_LEASE, "700 Lease Rd", "Arlington, TX 76001"),
    )
    monkeypatch.setattr(_client.requests, "get", lambda *a, **kw: _fake_response(html))

    result = _client.search_listings(listing_type="lease")
    assert result["total_returned"] == 1
    assert result["listings"][0]["listing_type"] == "For Lease"


def test_search_listings_listing_type_rent_alias(monkeypatch):
    """'rent' should map to For Lease listings."""
    html = _index_html(
        _card_html(_ARLINGTON_LEASE, "700 Lease Rd", "Arlington, TX 76001"),
    )
    monkeypatch.setattr(_client.requests, "get", lambda *a, **kw: _fake_response(html))

    result = _client.search_listings(listing_type="rent")
    assert result["total_returned"] == 1


def test_search_listings_listing_type_buy_alias(monkeypatch):
    """'buy' should map to For Sale listings."""
    html = _index_html(
        _card_html("church-property-for-sale-houston-tx-aaa", "100 Main St", "Houston, TX 77001"),
    )
    monkeypatch.setattr(_client.requests, "get", lambda *a, **kw: _fake_response(html))

    result = _client.search_listings(listing_type="buy")
    assert result["total_returned"] == 1


def test_search_listings_max_results(monkeypatch):
    cards = "".join(
        _card_html(f"church-property-for-sale-city-tx-{i}", f"{i} Main St", "Houston, TX 77001")
        for i in range(10)
    )
    html = _index_html(cards)
    monkeypatch.setattr(_client.requests, "get", lambda *a, **kw: _fake_response(html))

    result = _client.search_listings(max_results=3)
    assert result["total_returned"] == 3
    assert len(result["listings"]) == 3


def test_search_listings_price_always_none_on_index(monkeypatch):
    """Index page never has prices; price field must be None for all cards."""
    html = _index_html(
        _card_html("church-property-for-sale-houston-tx-aaa", "100 Main St", "Houston, TX 77001"),
    )
    monkeypatch.setattr(_client.requests, "get", lambda *a, **kw: _fake_response(html))

    result = _client.search_listings()
    assert all(li["price"] is None for li in result["listings"])


def test_search_listings_raises_on_no_cards(monkeypatch):
    monkeypatch.setattr(
        _client.requests, "get", lambda *a, **kw: _fake_response("<html><body></body></html>")
    )
    with pytest.raises(RuntimeError, match="Unexpected Church Realty response shape"):
        _client.search_listings()


# ---------- get_listing_details ----------


def test_get_listing_details_by_slug(monkeypatch):
    slug = "church-property-for-sale-houston-tx-10355-mills-road"
    html = _detail_html(
        slug=slug,
        h1="Church Property For Sale Houston TX",
        street="10355 Mills Road",
        addr2="Houston, TX 77070",
    )
    captured_urls = []

    def fake_get(url, *a, **kw):
        captured_urls.append(url)
        return _fake_response(html)

    monkeypatch.setattr(_client.requests, "get", fake_get)

    d = _client.get_listing_details(slug)
    assert d["listing_id"] == slug
    assert d["city"] == "Houston"
    assert d["state"] == "TX"
    assert d["price"] == 1500000.0
    assert d["description"] == "A great church property"
    assert d["building_sqft"] == 8000
    assert d["lot_acres"] == pytest.approx(2.5)
    assert d["year_built"] is None
    assert len(d["image_urls"]) == 2
    assert d["agent_name"] == "Jane Doe"
    assert "214-555-9999" in (d["agent_phone"] or "")
    assert f"/property/{slug}/" in captured_urls[0]


def test_get_listing_details_by_full_url(monkeypatch):
    slug = "church-property-for-sale-fort-worth-tx-3321-cleburne-road"
    html = _detail_html(
        slug=slug,
        h1="Church Property For Sale Fort Worth TX",
        street="3321 Cleburne Road",
        addr2="Fort Worth, TX 76110",
    )
    monkeypatch.setattr(_client.requests, "get", lambda *a, **kw: _fake_response(html))

    d = _client.get_listing_details(
        f"https://www.churchrealty.com/property/{slug}/"
    )
    assert d["listing_id"] == slug
    assert d["city"] == "Fort Worth"


def test_get_listing_details_by_int(monkeypatch):
    """int input must be accepted (_coerce_id converts it to string)."""
    html = _detail_html(
        slug="12345",
        h1="Some Property For Sale Dallas TX",
        street="12345 Test Blvd",
        addr2="Dallas, TX 75201",
    )
    monkeypatch.setattr(_client.requests, "get", lambda *a, **kw: _fake_response(html))

    d = _client.get_listing_details(12345)
    assert d["listing_id"] == "12345"


def test_get_listing_details_price_none_on_call_agent(monkeypatch):
    slug = "some-property-for-lease"
    html = _detail_html(
        slug=slug,
        h1="Some Property For Lease",
        street="999 Test St",
        addr2="Dallas, TX 75201",
        price_line="Price: Please call broker for price",
    )
    monkeypatch.setattr(_client.requests, "get", lambda *a, **kw: _fake_response(html))

    d = _client.get_listing_details(slug)
    assert d["price"] is None


# ---------- MCP tool wrappers ----------


def test_search_listings_tool_returns_dict(monkeypatch):
    html = _index_html(
        _card_html("church-property-for-sale-houston-tx-aaa", "100 Main St", "Houston, TX 77001"),
    )
    monkeypatch.setattr(_client.requests, "get", lambda *a, **kw: _fake_response(html))

    result = asyncio.run(server.search_listings(city="Houston"))
    assert result["total_returned"] == 1
    assert result["listings"][0]["city"] == "Houston"


def test_get_listing_details_tool_returns_dict(monkeypatch):
    slug = "church-property-for-sale-houston-tx-10355-mills-road"
    html = _detail_html(
        slug=slug,
        h1="Church Property For Sale Houston TX",
        street="10355 Mills Road",
        addr2="Houston, TX 77070",
    )
    monkeypatch.setattr(_client.requests, "get", lambda *a, **kw: _fake_response(html))

    result = asyncio.run(server.get_listing_details(slug))
    assert result["listing_id"] == slug
    assert result["city"] == "Houston"
