"""End-to-end tests for the Airbnb client with mocked HTTP."""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from realestate_mcp.servers.airbnb import _client, server


@pytest.fixture(autouse=True)
def _reset_client_state(monkeypatch):
    """Clear the in-process geocode cache and rate-limit timer between tests."""
    monkeypatch.setattr(_client, "_geocode_cache", {})
    monkeypatch.setattr(_client, "_last_nominatim_call", 0.0)


def _fake_response(json_data: Any = None, html: str | None = None, status: int = 200):
    r = MagicMock()
    r.status_code = status
    r.raise_for_status = MagicMock()
    if json_data is not None:
        r.json = MagicMock(return_value=json_data)
    if html is not None:
        r.text = html
    return r


def _nominatim_response(name: str = "Test City") -> Any:
    return [
        {
            "boundingbox": ["35.5", "35.7", "-82.7", "-82.4"],
            "display_name": name,
        }
    ]


def _make_listing_id(numeric: str) -> str:
    return base64.b64encode(f"DemandStayListing:{numeric}".encode()).decode()


def _build_search_html(
    listings: list[dict[str, Any]], cursors: list[str] | None = None
) -> str:
    """Wrap a search payload in HTML with the script tag the parser expects."""
    payload = {
        "niobeClientData": [
            [
                "Key",
                {
                    "data": {
                        "presentation": {
                            "staysSearch": {
                                "results": {
                                    "searchResults": listings,
                                    "paginationInfo": {
                                        "pageCursors": cursors or ["c0", "c1"]
                                    },
                                }
                            }
                        }
                    }
                },
            ]
        ]
    }
    return (
        f'<html><body><script id="data-deferred-state-0" type="application/json">'
        f"{json.dumps(payload)}"
        f"</script></body></html>"
    )


def _listing_dict(
    *,
    id_: str,
    bedrooms: int = 2,
    price: str = "$1,000",
) -> dict[str, Any]:
    return {
        "demandStayListing": {
            "id": _make_listing_id(id_),
            "location": {"coordinate": {"latitude": 35.5, "longitude": -82.5}},
        },
        "structuredContent": {
            "primaryLine": [
                {"body": f"{bedrooms} bedrooms"},
                {"body": f"{bedrooms} beds"},
                {"body": "1 bath"},
            ]
        },
        "structuredDisplayPrice": {"primaryLine": {"discountedPrice": price}},
        "title": "Home in Test",
        "subtitle": f"Listing {id_}",
        "avgRatingLocalized": "4.8 (50)",
        "contextualPictures": [{"picture": "https://img.example/x.jpg"}],
    }


# ---------- geocode_city ----------


def test_geocode_city_caches_results(monkeypatch):
    calls = []

    def fake_get(url, *args, **kwargs):
        calls.append(url)
        return _fake_response(json_data=_nominatim_response("Asheville, NC"))

    monkeypatch.setattr(_client.requests, "get", fake_get)

    bbox1 = _client.geocode_city("Asheville, NC")
    bbox2 = _client.geocode_city("Asheville, NC")
    bbox3 = _client.geocode_city("ASHEVILLE, nc")  # case-insensitive cache

    assert len(calls) == 1
    assert bbox1 is bbox2 is bbox3
    assert bbox1.sw_lat == 35.5
    assert bbox1.ne_lat == 35.7


def test_geocode_city_raises_on_no_result(monkeypatch):
    monkeypatch.setattr(_client.requests, "get", lambda *a, **kw: _fake_response(json_data=[]))
    with pytest.raises(ValueError, match="No geocoding result"):
        _client.geocode_city("Atlantis")


# ---------- search_stays orchestration ----------


def test_search_stays_single_page(monkeypatch):
    listings = [_listing_dict(id_=str(i)) for i in range(3)]
    html = _build_search_html(listings, cursors=["c0"])

    def fake_get(url, *args, **kwargs):
        if "nominatim" in url:
            return _fake_response(json_data=_nominatim_response("Asheville"))
        return _fake_response(html=html)

    monkeypatch.setattr(_client.requests, "get", fake_get)

    result = _client.search_stays(
        city="Asheville",
        check_in="2026-06-01",
        nights=3,
        max_results=50,
    )
    assert result["total_returned"] == 3
    assert {li["listing_id"] for li in result["listings"]} == {"0", "1", "2"}


def test_search_stays_paginates_and_dedupes(monkeypatch):
    page1_html = _build_search_html(
        [_listing_dict(id_="1"), _listing_dict(id_="2")],
        cursors=["c0", "c1"],
    )
    page2_html = _build_search_html(
        [_listing_dict(id_="2"), _listing_dict(id_="3")],  # "2" duplicates page 1
        cursors=["c0", "c1"],
    )
    pages = [page1_html, page2_html]
    page_calls = []

    def fake_get(url, *args, **kwargs):
        if "nominatim" in url:
            return _fake_response(json_data=_nominatim_response())
        page_calls.append(url)
        return _fake_response(html=pages[len(page_calls) - 1])

    monkeypatch.setattr(_client.requests, "get", fake_get)

    result = _client.search_stays(
        city="Test", check_in="2026-06-01", nights=2, max_results=50
    )
    ids = [li["listing_id"] for li in result["listings"]]
    assert ids == ["1", "2", "3"]
    assert len(page_calls) == 2
    # Page 2's URL should carry a cursor query param
    assert "cursor=c1" in page_calls[1]


def test_search_stays_client_side_price_filter(monkeypatch):
    listings = [
        _listing_dict(id_="cheap", price="$300"),  # $300 / 3n = $100/n
        _listing_dict(id_="mid", price="$900"),  # $900 / 3n = $300/n
        _listing_dict(id_="expensive", price="$1,500"),  # $500/n
    ]
    html = _build_search_html(listings, cursors=["c0"])

    def fake_get(url, *args, **kwargs):
        if "nominatim" in url:
            return _fake_response(json_data=_nominatim_response())
        return _fake_response(html=html)

    monkeypatch.setattr(_client.requests, "get", fake_get)

    result = _client.search_stays(
        city="Test",
        check_in="2026-06-01",
        nights=3,
        price_max=350,  # nightly cap
        max_results=50,
    )
    ids = [li["listing_id"] for li in result["listings"]]
    assert "cheap" in ids
    assert "mid" in ids
    assert "expensive" not in ids


def test_search_stays_client_side_price_min_filter(monkeypatch):
    listings = [
        _listing_dict(id_="cheap", price="$300"),
        _listing_dict(id_="mid", price="$900"),
    ]
    html = _build_search_html(listings, cursors=["c0"])

    def fake_get(url, *args, **kwargs):
        if "nominatim" in url:
            return _fake_response(json_data=_nominatim_response())
        return _fake_response(html=html)

    monkeypatch.setattr(_client.requests, "get", fake_get)

    result = _client.search_stays(
        city="Test",
        check_in="2026-06-01",
        nights=3,
        price_min=200,  # $200/n minimum -> $600 minimum total
        max_results=50,
    )
    ids = [li["listing_id"] for li in result["listings"]]
    assert ids == ["mid"]


def test_search_stays_requires_check_out_or_nights(monkeypatch):
    monkeypatch.setattr(
        _client.requests, "get", lambda *a, **kw: _fake_response(json_data=_nominatim_response())
    )
    with pytest.raises(ValueError, match="check_out or nights"):
        _client.search_stays(city="Test", check_in="2026-06-01")


def test_search_stays_requires_check_in():
    with pytest.raises(ValueError, match="check_in is required"):
        _client.search_stays(city="Test", nights=3)


def test_search_stays_check_out_after_check_in(monkeypatch):
    monkeypatch.setattr(
        _client.requests, "get", lambda *a, **kw: _fake_response(json_data=_nominatim_response())
    )
    with pytest.raises(ValueError, match="check_out must be after"):
        _client.search_stays(city="Test", check_in="2026-06-05", check_out="2026-06-01")


def test_search_stays_uses_nights_to_compute_check_out(monkeypatch):
    captured_urls = []

    def fake_get(url, *args, **kwargs):
        if "nominatim" in url:
            return _fake_response(json_data=_nominatim_response())
        captured_urls.append(url)
        return _fake_response(html=_build_search_html([_listing_dict(id_="1")], cursors=["c0"]))

    monkeypatch.setattr(_client.requests, "get", fake_get)
    result = _client.search_stays(city="Test", check_in="2026-06-01", nights=5, max_results=10)
    assert result["listings"][0]["check_out"] == "2026-06-06"
    assert result["listings"][0]["nights"] == 5
    assert "checkin=2026-06-01" in captured_urls[0]
    assert "checkout=2026-06-06" in captured_urls[0]


# ---------- get_listing_details ----------


def _details_html(listing_id: str = "9999") -> str:
    payload = {
        "niobeClientData": [
            [
                "Key",
                {
                    "data": {
                        "presentation": {
                            "stayProductDetailPage": {
                                "sections": {
                                    "sections": [
                                        {
                                            "sectionId": "TITLE_DEFAULT",
                                            "section": {"title": "Mocked Title"},
                                        },
                                        {
                                            "sectionId": "BOOK_IT_SIDEBAR",
                                            "section": {"maxGuestCapacity": 4},
                                        },
                                        {
                                            "sectionId": "HERO_DEFAULT",
                                            "section": {
                                                "previewImages": [
                                                    {"baseUrl": "https://img/1.jpg"}
                                                ]
                                            },
                                        },
                                    ]
                                }
                            }
                        },
                        "node": {"pdpPresentation": {"mediaTour": {"stops": []}}},
                    }
                },
            ]
        ]
    }
    return (
        '<html><script id="data-deferred-state-0" type="application/json">'
        f"{json.dumps(payload)}"
        "</script></html>"
    )


def test_get_listing_details_by_id(monkeypatch):
    captured = []

    def fake_get(url, *args, **kwargs):
        captured.append(url)
        return _fake_response(html=_details_html())

    monkeypatch.setattr(_client.requests, "get", fake_get)

    d = _client.get_listing_details("9999")
    assert d["listing_id"] == "9999"
    assert d["url"] == "https://www.airbnb.com/rooms/9999"
    assert d["title"] == "Mocked Title"
    assert d["max_guests"] == 4
    assert d["image_urls"] == ["https://img/1.jpg"]
    assert "/rooms/9999" in captured[0]


def test_get_listing_details_by_url(monkeypatch):
    monkeypatch.setattr(
        _client.requests, "get", lambda *a, **kw: _fake_response(html=_details_html())
    )
    d = _client.get_listing_details("https://www.airbnb.com/rooms/12345")
    assert d["listing_id"] == "12345"


# ---------- MCP tool: check_in_dates parallel merge ----------


def test_search_stays_tool_check_in_dates_merges_cheapest(monkeypatch):
    """The MCP tool fans out per date in parallel, then keeps each listing's cheapest option."""
    page_by_checkin = {
        "2026-07-11": _build_search_html(
            [
                {**_listing_dict(id_="A", price="$1,500"), "subtitle": "A"},
                {**_listing_dict(id_="B", price="$2,000"), "subtitle": "B"},
            ],
            cursors=["c0"],
        ),
        "2026-07-12": _build_search_html(
            [
                {**_listing_dict(id_="A", price="$1,300"), "subtitle": "A"},  # cheaper here
                {**_listing_dict(id_="C", price="$1,800"), "subtitle": "C"},  # only on Sun
            ],
            cursors=["c0"],
        ),
    }

    def fake_get(url, *args, **kwargs):
        if "nominatim" in url:
            return _fake_response(json_data=_nominatim_response())
        for ci, html in page_by_checkin.items():
            if f"checkin={ci}" in url:
                return _fake_response(html=html)
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(_client.requests, "get", fake_get)

    result = asyncio.run(
        server.search_stays(
            city="Test",
            check_in_dates=["2026-07-11", "2026-07-12"],
            nights=7,
            max_results=10,
        )
    )
    by_id = {li["listing_id"]: li for li in result["listings"]}
    assert by_id["A"]["total_price"] == 1300
    assert by_id["A"]["check_in"] == "2026-07-12"
    assert by_id["B"]["total_price"] == 2000
    assert by_id["B"]["check_in"] == "2026-07-11"
    assert by_id["C"]["total_price"] == 1800
    assert by_id["C"]["check_in"] == "2026-07-12"


def test_search_stays_tool_rejects_both_check_in_forms():
    with pytest.raises(ValueError, match="not both"):
        asyncio.run(
            server.search_stays(
                city="Test",
                check_in="2026-07-11",
                check_in_dates=["2026-07-12"],
                nights=7,
            )
        )


def test_search_stays_tool_check_in_dates_requires_nights():
    with pytest.raises(ValueError, match="nights is required"):
        asyncio.run(
            server.search_stays(
                city="Test",
                check_in_dates=["2026-07-11"],
            )
        )


def test_search_stays_tool_requires_at_least_one_check_in():
    with pytest.raises(ValueError, match="check_in or check_in_dates"):
        asyncio.run(server.search_stays(city="Test", nights=3))
