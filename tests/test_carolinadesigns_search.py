"""End-to-end integration tests for the Carolina Designs client with mocked HTTP."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest

from realestate_mcp.servers.carolinadesigns import _client, server


def _fake_response(json_data: Any = None, status: int = 200) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.raise_for_status = MagicMock()
    r.json = MagicMock(return_value=json_data)
    return r


def _search_payload(items: list[dict], title: str = "Corolla Vacation Rentals") -> dict:
    return {
        "Results": items,
        "SearchArgs": {"SearchType": "32"},
        "SearchDescription": f" ({len(items)} results)",
        "Title": title,
        "ZeroResultsText": None,
    }


def _item(propid: str, bedrooms: int = 4, baths: str = "4/1") -> dict:
    return {
        "Propid": propid,
        "Propname": f"HOUSE {propid}",
        "Bedrooms": bedrooms,
        "Baths": baths,
        "PropURL": f"/corolla-vacation-rental/{propid}-test/",
        "DisplayLocation": "Oceanfront",
        "DisplaySub": "Whalehead in Corolla",
        "ImageURL": f"https://img.example/{propid}.jpg",
        "PetFriendly": False,
        "PrivatePool": False,
        "WeeklyRate": None,
        "TopAmenities": [],
    }


def _detail_payload(propid: str = "161") -> dict:
    return {
        "Propid": propid,
        "Propname": f"HOUSE {propid}",
        "Area": "Corolla",
        "NumBedrooms": "6",
        "NumBathrooms": "6.10",
        "Bathroominfo": ["Full Bathrooms: 6", "Half Bathrooms 1"],
        "Sleeps": "12",
        "Description": "<p>A great house</p>",
        "Sidebar": [{"Title": "Overview", "Items": ["6 Bedrooms", "Hot Tub"]}],
        "PicsLarge": [{"ImgDesc": "Front", "ImgUrl": "https://img.example/front.jpg"}],
        "Weeks1CurrAvail": [
            {
                "ArrivalDate": "5/9/2026",
                "Rate": "$2,800.00",
                "CostPerNight": "$400.00",
                "Orate": "$3,500.00",
                "BookType": "NORM",
                "PetFeeDefaultChecked": False,
            }
        ],
        "Weeks2CurrAvail": None,
        "MinPrice": 2800,
        "MaxPrice": 5600,
        "CanonicalUrl": f"https://www.carolinadesigns.com/corolla-vacation-rental/{propid}-test/",
    }


# ---------- search_rentals ----------


def test_search_rentals_returns_all_listings(monkeypatch):
    items = [_item(str(i)) for i in range(5)]
    payload = _search_payload(items)

    monkeypatch.setattr(_client.requests, "get", lambda *a, **kw: _fake_response(payload))

    result = _client.search_rentals("corolla")
    assert result["total_returned"] == 5
    assert {li["listing_id"] for li in result["listings"]} == {"0", "1", "2", "3", "4"}


def test_search_rentals_min_bedrooms_filter(monkeypatch):
    items = [
        _item("small", bedrooms=3),
        _item("medium", bedrooms=5),
        _item("large", bedrooms=8),
    ]
    def fake_get(*a, **kw):
        return _fake_response(_search_payload(items))

    monkeypatch.setattr(_client.requests, "get", fake_get)

    result = _client.search_rentals("corolla", min_bedrooms=5)
    ids = [li["listing_id"] for li in result["listings"]]
    assert "small" not in ids
    assert "medium" in ids
    assert "large" in ids


def test_search_rentals_max_results_cap(monkeypatch):
    items = [_item(str(i)) for i in range(20)]
    monkeypatch.setattr(
        _client.requests, "get", lambda *a, **kw: _fake_response(_search_payload(items))
    )

    result = _client.search_rentals("corolla", max_results=5)
    assert result["total_returned"] == 5
    assert len(result["listings"]) == 5


def test_search_rentals_uses_correct_town_id(monkeypatch):
    captured_urls = []

    def fake_get(url, *args, **kwargs):
        captured_urls.append(url)
        return _fake_response(_search_payload([]))

    monkeypatch.setattr(_client.requests, "get", fake_get)

    _client.search_rentals("duck")
    assert "/33/" in captured_urls[0]

    _client.search_rentals("nags-head")
    assert "/37/" in captured_urls[1]


def test_search_rentals_raises_on_unknown_town():
    with pytest.raises(ValueError, match="Unknown town"):
        _client.search_rentals("bermuda")


def test_search_rentals_raises_on_schema_drift(monkeypatch):
    monkeypatch.setattr(
        _client.requests, "get", lambda *a, **kw: _fake_response({"bad": "shape"})
    )
    with pytest.raises(RuntimeError, match="Unexpected Carolina Designs response shape"):
        _client.search_rentals("corolla")


def test_search_rentals_includes_search_area_in_response(monkeypatch):
    monkeypatch.setattr(
        _client.requests,
        "get",
        lambda *a, **kw: _fake_response(_search_payload([], title="Corolla Vacation Rentals")),
    )
    result = _client.search_rentals("corolla")
    assert result["search_area"] == "Corolla Vacation Rentals"


# ---------- get_rental_details ----------


def test_get_rental_details_by_id(monkeypatch):
    captured = []

    def fake_get(url, *args, **kwargs):
        captured.append(url)
        return _fake_response(_detail_payload("161"))

    monkeypatch.setattr(_client.requests, "get", fake_get)

    d = _client.get_rental_details("161")
    assert d["listing_id"] == "161"
    assert d["bedrooms"] == 6
    assert d["bathrooms_full"] == 6
    assert d["bathrooms_half"] == 1
    assert d["sleeps"] == 12
    assert "great house" in d["description"].lower()
    assert "/161" in captured[0]


def test_get_rental_details_by_canonical_url(monkeypatch):
    monkeypatch.setattr(
        _client.requests, "get", lambda *a, **kw: _fake_response(_detail_payload("054"))
    )
    d = _client.get_rental_details(
        "https://www.carolinadesigns.com/corolla-vacation-rental/054-moon-glow/"
    )
    assert d["listing_id"] == "054"


def test_get_rental_details_weekly_rates_present(monkeypatch):
    monkeypatch.setattr(
        _client.requests, "get", lambda *a, **kw: _fake_response(_detail_payload("161"))
    )
    d = _client.get_rental_details("161")
    assert len(d["weekly_rates"]) == 1
    assert d["weekly_rates"][0]["arrival_date"] == "5/9/2026"
    assert d["weekly_rates"][0]["weekly_rate"] == "$2,800.00"
    assert d["weekly_rates"][0]["nightly_rate"] == "$400.00"


def test_get_rental_details_image_urls(monkeypatch):
    monkeypatch.setattr(
        _client.requests, "get", lambda *a, **kw: _fake_response(_detail_payload("161"))
    )
    d = _client.get_rental_details("161")
    assert d["image_urls"] == ["https://img.example/front.jpg"]


def test_get_rental_details_raises_on_schema_drift(monkeypatch):
    monkeypatch.setattr(
        _client.requests, "get", lambda *a, **kw: _fake_response({"bad": "shape"})
    )
    with pytest.raises(RuntimeError, match="Unexpected Carolina Designs response shape"):
        _client.get_rental_details("161")


# ---------- MCP server tools ----------


def test_mcp_search_rentals_tool(monkeypatch):
    items = [_item("A", bedrooms=5), _item("B", bedrooms=3)]
    monkeypatch.setattr(
        _client.requests, "get", lambda *a, **kw: _fake_response(_search_payload(items))
    )
    result = asyncio.run(server.search_rentals(town="corolla", min_bedrooms=4))
    ids = [li["listing_id"] for li in result["listings"]]
    assert "A" in ids
    assert "B" not in ids


def test_mcp_get_rental_details_tool(monkeypatch):
    monkeypatch.setattr(
        _client.requests, "get", lambda *a, **kw: _fake_response(_detail_payload("999"))
    )
    result = asyncio.run(server.get_rental_details("999"))
    assert result["listing_id"] == "999"
    assert result["bedrooms"] == 6
