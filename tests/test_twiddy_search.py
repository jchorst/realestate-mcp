"""End-to-end integration tests for the Twiddy client with mocked HTTP."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest

from realestate_mcp.servers.twiddy import _client, server


def _fake_response(json_data: Any = None, status: int = 200) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.raise_for_status = MagicMock()
    r.json = MagicMock(return_value=json_data)
    return r


def _search_payload(items: list[dict]) -> dict:
    return {"isSameDayArrival": False, "results": items}


def _item(
    prop_id: int,
    name: str = "",
    bedrooms: int = 4,
    town: str = "Corolla",
    distance_to_beach: str = "3rd Row",
) -> dict:
    return {
        "propertyId": prop_id,
        "propertyName": name or f"House {prop_id}",
        "propertyNumber": f"C{prop_id:04d}",
        "propertyUrl": f"/outer-banks/corolla/whalehead/rentals/house-{prop_id}/",
        "rating": None,
        "town": town,
        "bedrooms": f"{bedrooms} beds",
        "distanceToBeach": distance_to_beach,
        "locationItems": [],
        "amenityItems": [
            {
                "label": f"{bedrooms} bedrooms",
                "description": f"(Sleeps {bedrooms * 2})",
                "match": False,
            }
        ],
        "checkInItem": {"label": "Saturday check-in", "description": None, "match": False},
        "saves": 0,
        "lat": 36.1,
        "lon": -75.8,
        "isSaved": False,
        "badges": [],
        "images": [f"{prop_id}00?v=abc"],
        "availabilityBadges": [],
        "price": None,
        "isAvailable": True,
    }


def _info_payload(prop_id: int = 5744) -> dict:
    return {
        "propertyID": prop_id,
        "unitNumber": "E400",
        "name": f"House {prop_id}",
        "city": "Corolla",
        "state": "NC",
        "zip": "27927",
        "description": "<p>A wonderful beach house.</p>",
        "neighborhood": "Whalehead",
        "location": "Oceanfront",
        "fullUrl": f"/outer-banks/corolla/whalehead/rentals/house-{prop_id}/",
        "exteriorImage": f"https://www.twiddy.com/rns/unitimages.twd/{prop_id}.jpg",
        "bedrooms": 6,
        "fullBaths": 6,
        "partialBaths": 1,
        "totalBaths": 7,
        "distanceToBeach": None,
    }


def _amenities_payload() -> dict:
    return {
        "sectionModel": {
            "featuredAmenities": [
                {"displayLabel": "Private Pool"},
                {"displayLabel": "Pets Allowed"},
                {"displayLabel": "Hot Tub"},
            ],
        },
        "bathroomsSummary": "6 Full 1 Half",
        "bathroomsTotal": 7,
        "bedrooms": 6,
        "sleepsCount": 14,
    }


def _calendar_payload() -> dict:
    return {
        "calculatorWeeklyRate": 0,
        "amenityYear": 2026,
        "availabilityYears": [
            {
                "year": 2026,
                "selected": True,
                "months": [
                    {
                        "monthTitle": "May 2026",
                        "monthNum": 5,
                        "year": 2026,
                        "month": "May",
                        "weeks": [
                            {
                                "arrive": "2026-05-09T00:00:00",
                                "depart": "2026-05-16T00:00:00",
                                "weekContent": "Weekly Rate $3,500",
                                "weeklyRate": 3500.0,
                                "isAvailable": True,
                            }
                        ],
                    }
                ],
            }
        ],
    }


# ---------- search_rentals ----------


def test_search_rentals_returns_listings(monkeypatch):
    items = [_item(i + 100) for i in range(5)]
    monkeypatch.setattr(
        _client.requests, "post", lambda *a, **kw: _fake_response(_search_payload(items))
    )

    result = _client.search_rentals("corolla")
    assert result["total_returned"] == 5
    ids = {li["listing_id"] for li in result["listings"]}
    assert ids == {100, 101, 102, 103, 104}


def test_search_rentals_min_bedrooms_filter(monkeypatch):
    items = [
        _item(1, bedrooms=3),
        _item(2, bedrooms=5),
        _item(3, bedrooms=8),
    ]
    monkeypatch.setattr(
        _client.requests, "post", lambda *a, **kw: _fake_response(_search_payload(items))
    )
    result = _client.search_rentals("corolla", min_bedrooms=5)
    ids = [li["listing_id"] for li in result["listings"]]
    assert 1 not in ids
    assert 2 in ids
    assert 3 in ids


def test_search_rentals_max_results_cap(monkeypatch):
    items = [_item(i) for i in range(20)]
    monkeypatch.setattr(
        _client.requests, "post", lambda *a, **kw: _fake_response(_search_payload(items))
    )
    result = _client.search_rentals("corolla", max_results=7)
    assert result["total_returned"] == 7
    assert len(result["listings"]) == 7


def test_search_rentals_sends_correct_town_criteria(monkeypatch):
    captured_bodies = []

    def fake_post(url, *args, **kwargs):
        captured_bodies.append(kwargs.get("json") or {})
        return _fake_response(_search_payload([]))

    monkeypatch.setattr(_client.requests, "post", fake_post)

    _client.search_rentals("duck")
    assert captured_bodies[0]["townCriteria"] == [{"criteriaName": "Duck"}]

    _client.search_rentals("southern-shores")
    assert captured_bodies[1]["townCriteria"] == [{"criteriaName": "Southern Shores"}]


def test_search_rentals_raises_on_unknown_town():
    with pytest.raises(ValueError, match="Unknown town"):
        _client.search_rentals("bermuda")


def test_search_rentals_raises_on_schema_drift(monkeypatch):
    monkeypatch.setattr(
        _client.requests, "post", lambda *a, **kw: _fake_response({"bad": "shape"})
    )
    with pytest.raises(RuntimeError, match="Unexpected Twiddy response shape"):
        _client.search_rentals("corolla")


def test_search_rentals_includes_search_area(monkeypatch):
    monkeypatch.setattr(
        _client.requests, "post", lambda *a, **kw: _fake_response(_search_payload([]))
    )
    result = _client.search_rentals("corolla")
    assert "Corolla" in result["search_area"]
    assert "Outer Banks" in result["search_area"]


def test_search_rentals_oceanfront_flag(monkeypatch):
    items = [
        _item(1, distance_to_beach="Oceanfront"),
        _item(2, distance_to_beach="Semi-Oceanfront"),
    ]
    monkeypatch.setattr(
        _client.requests, "post", lambda *a, **kw: _fake_response(_search_payload(items))
    )
    result = _client.search_rentals("corolla")
    oceanfront = {li["listing_id"]: li["oceanfront"] for li in result["listings"]}
    assert oceanfront[1] is True
    assert oceanfront[2] is False


def test_search_rentals_image_url_constructed(monkeypatch):
    items = [_item(5744)]
    monkeypatch.setattr(
        _client.requests, "post", lambda *a, **kw: _fake_response(_search_payload(items))
    )
    result = _client.search_rentals("corolla")
    img = result["listings"][0]["image_url"]
    assert img is not None
    assert "twiddy.com/property-images/" in img


# ---------- get_rental_details ----------


def _mock_get_sequence(responses: list[Any]):
    """Return a fake GET that yields responses in order."""
    responses_iter = iter(responses)

    def fake_get(url, *args, **kwargs):
        return _fake_response(next(responses_iter))

    return fake_get


def test_get_rental_details_by_id(monkeypatch):
    captured_urls = []

    def fake_get(url, *args, **kwargs):
        captured_urls.append(url)
        if "Info" in url:
            return _fake_response(_info_payload(5744))
        if "Amenities" in url:
            return _fake_response(_amenities_payload())
        if "Calendar" in url:
            return _fake_response(_calendar_payload())
        return _fake_response({})

    monkeypatch.setattr(_client.requests, "get", fake_get)

    d = _client.get_rental_details("5744")
    assert d["listing_id"] == 5744
    assert d["bedrooms"] == 6
    assert d["bathrooms_full"] == 6
    assert d["bathrooms_half"] == 1
    assert d["sleeps"] == 14
    assert "beach house" in d["description"].lower() or len(d["description"]) > 0
    assert any("Info" in u for u in captured_urls)
    assert any("Amenities" in u for u in captured_urls)
    assert any("Calendar" in u for u in captured_urls)


def test_get_rental_details_amenities_list(monkeypatch):
    def fake_get(url, *args, **kwargs):
        if "Info" in url:
            return _fake_response(_info_payload(5744))
        if "Amenities" in url:
            return _fake_response(_amenities_payload())
        if "Calendar" in url:
            return _fake_response(_calendar_payload())
        return _fake_response({})

    monkeypatch.setattr(_client.requests, "get", fake_get)

    d = _client.get_rental_details("5744")
    assert "Private Pool" in d["amenities"]
    assert "Pets Allowed" in d["amenities"]
    assert "Hot Tub" in d["amenities"]


def test_get_rental_details_weekly_rates(monkeypatch):
    def fake_get(url, *args, **kwargs):
        if "Info" in url:
            return _fake_response(_info_payload(5744))
        if "Amenities" in url:
            return _fake_response(_amenities_payload())
        if "Calendar" in url:
            return _fake_response(_calendar_payload())
        return _fake_response({})

    monkeypatch.setattr(_client.requests, "get", fake_get)

    d = _client.get_rental_details("5744")
    assert len(d["weekly_rates"]) == 1
    assert d["weekly_rates"][0]["arrive"] == "2026-05-09"
    assert d["weekly_rates"][0]["weekly_rate"] == 3500.0
    assert d["weekly_rates"][0]["is_available"] is True


def test_get_rental_details_image_urls(monkeypatch):
    def fake_get(url, *args, **kwargs):
        if "Info" in url:
            return _fake_response(_info_payload(5744))
        if "Amenities" in url:
            return _fake_response(_amenities_payload())
        if "Calendar" in url:
            return _fake_response(_calendar_payload())
        return _fake_response({})

    monkeypatch.setattr(_client.requests, "get", fake_get)

    d = _client.get_rental_details("5744")
    assert len(d["image_urls"]) >= 1
    assert "twiddy.com" in d["image_urls"][0]


def test_get_rental_details_raises_on_schema_drift(monkeypatch):
    def fake_get(url, *args, **kwargs):
        return _fake_response({"bad": "shape"})

    monkeypatch.setattr(_client.requests, "get", fake_get)

    with pytest.raises(RuntimeError, match="Unexpected Twiddy response shape"):
        _client.get_rental_details("5744")


# ---------- MCP server tools ----------


def test_mcp_search_rentals_tool(monkeypatch):
    items = [_item(10, bedrooms=6), _item(11, bedrooms=3)]
    monkeypatch.setattr(
        _client.requests, "post", lambda *a, **kw: _fake_response(_search_payload(items))
    )
    result = asyncio.run(server.search_rentals(town="corolla", min_bedrooms=5))
    ids = [li["listing_id"] for li in result["listings"]]
    assert 10 in ids
    assert 11 not in ids


def test_mcp_get_rental_details_tool(monkeypatch):
    def fake_get(url, *args, **kwargs):
        if "Info" in url:
            return _fake_response(_info_payload(999))
        if "Amenities" in url:
            return _fake_response(_amenities_payload())
        if "Calendar" in url:
            return _fake_response(_calendar_payload())
        return _fake_response({})

    monkeypatch.setattr(_client.requests, "get", fake_get)

    result = asyncio.run(server.get_rental_details("999"))
    assert result["listing_id"] == 999
    assert result["bedrooms"] == 6
