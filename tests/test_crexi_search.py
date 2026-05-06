"""End-to-end tests for the Crexi client with mocked HTTP."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest

from realestate_mcp.servers.crexi import _client, server


def _fake_response(
    json_data: Any = None,
    status: int = 200,
) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.raise_for_status = MagicMock()
    if json_data is not None:
        r.json = MagicMock(return_value=json_data)
    return r


def _search_item(
    id_: int = 1,
    name: str = "Church Property",
    types: list[str] | None = None,
    asking_price: float | None = 500000.0,
    sqft: int | None = 5000,
    city: str = "Nashville",
    state: str = "TN",
    zip_: str = "37201",
    url_slug: str = "tennessee-church-property",
) -> dict[str, Any]:
    return {
        "id": id_,
        "name": name,
        "description": "Special Purpose",
        "thumbnailUrl": f"https://images.crexi.com/assets/{id_}/thumb.jpg",
        "urlSlug": url_slug,
        "askingPrice": asking_price,
        "squareFootage": sqft,
        "types": types or ["Special Purpose"],
        "status": "On-Market",
        "brokerageName": "Test Realty",
        "locations": [
            {
                "address": "123 Main St",
                "city": city,
                "state": {"code": state},
                "zip": zip_,
                "latitude": 36.16,
                "longitude": -86.78,
            }
        ],
        "isNew": False,
    }


def _search_response(items: list[dict]) -> dict[str, Any]:
    return {"data": items, "totalCount": len(items)}


def _asset_detail(
    id_: int = 1,
    name: str = "Church Property",
    types: list[str] | None = None,
    asking_price: float | None = 500000.0,
    url_slug: str = "tennessee-church-property",
) -> dict[str, Any]:
    return {
        "id": id_,
        "name": name,
        "types": types or ["Special Purpose"],
        "status": "Active",
        "urlSlug": url_slug,
        "askingPrice": asking_price,
        "thumbnailUrl": f"https://images.crexi.com/assets/{id_}/thumb.jpg",
        "marketingDescription": "<p>A beautiful property for sale.</p>",
        "description": "Special Purpose",
        "details": {
            "Year Built": "1965",
            "Lot Size (acres)": "1.2",
            "Square Footage": "5,000",
        },
        "summaryDetails": [
            {"key": "SquareFootage", "value": 5000, "display": "5,000"},
            {"key": "AskingPrice", "value": asking_price, "display": "$500,000"},
        ],
        "locations": [
            {
                "address": "123 Main St",
                "city": "Nashville",
                "county": "Davidson",
                "state": {"code": "TN", "name": "Tennessee"},
                "zip": "37201",
                "latitude": 36.16,
                "longitude": -86.78,
            }
        ],
        "isUnpriced": False,
        "hasBrokerOfRecord": False,
        "brokerProducts": [],
    }


def _gallery_response(asset_id: int = 1) -> list[dict[str, Any]]:
    return [
        {
            "id": 100,
            "type": "Image",
            "imageUrl": f"https://images.crexi.com/assets/{asset_id}/img1.jpg",
            "mediumTnUrl": f"https://images.crexi.com/assets/{asset_id}/img1_tn.jpg",
        },
        {
            "id": 101,
            "type": "Image",
            "imageUrl": f"https://images.crexi.com/assets/{asset_id}/img2.jpg",
            "mediumTnUrl": f"https://images.crexi.com/assets/{asset_id}/img2_tn.jpg",
        },
    ]


def _brokers_response(first: str = "John", last: str = "Smith") -> list[dict[str, Any]]:
    return [
        {
            "id": 9999,
            "firstName": first,
            "lastName": last,
            "brokerage": {"name": "Test Realty", "location": {}},
            "licenses": ["TN 12345"],
        }
    ]


# ---------- search_properties ----------


def test_search_properties_basic(monkeypatch):
    items = [_search_item(id_=i) for i in range(1, 4)]
    calls = []

    def fake_post(url, *args, **kwargs):
        calls.append(url)
        return _fake_response(json_data=_search_response(items))

    monkeypatch.setattr(_client.requests, "post", fake_post)

    result = _client.search_properties("church", max_results=50)
    assert result["search_query"] == "church"
    assert result["total_returned"] == 3
    assert len(result["properties"]) == 3
    assert result["properties"][0]["listing_id"] == "1"
    assert result["properties"][0]["city"] == "Nashville"
    assert result["properties"][0]["state"] == "TN"
    assert len(calls) == 1
    assert "assets/search" in calls[0]


def test_search_properties_requires_query():
    with pytest.raises(ValueError, match="query is required"):
        _client.search_properties("")


def test_search_properties_client_side_price_filter_max(monkeypatch):
    items = [
        _search_item(id_=1, asking_price=200000.0),
        _search_item(id_=2, asking_price=800000.0),
        _search_item(id_=3, asking_price=2000000.0),
    ]
    monkeypatch.setattr(
        _client.requests, "post", lambda *a, **kw: _fake_response(json_data=_search_response(items))
    )

    result = _client.search_properties("church", max_price=1000000)
    ids = [p["listing_id"] for p in result["properties"]]
    assert "1" in ids
    assert "2" in ids
    assert "3" not in ids


def test_search_properties_client_side_price_filter_min(monkeypatch):
    items = [
        _search_item(id_=1, asking_price=100000.0),
        _search_item(id_=2, asking_price=500000.0),
    ]
    monkeypatch.setattr(
        _client.requests, "post", lambda *a, **kw: _fake_response(json_data=_search_response(items))
    )

    result = _client.search_properties("church", min_price=300000)
    ids = [p["listing_id"] for p in result["properties"]]
    assert "1" not in ids
    assert "2" in ids


def test_search_properties_client_side_property_type_filter(monkeypatch):
    items = [
        _search_item(id_=1, types=["Special Purpose"]),
        _search_item(id_=2, types=["Land"]),
        _search_item(id_=3, types=["Office"]),
    ]
    monkeypatch.setattr(
        _client.requests, "post", lambda *a, **kw: _fake_response(json_data=_search_response(items))
    )

    result = _client.search_properties("church", property_type="Special Purpose")
    ids = [p["listing_id"] for p in result["properties"]]
    assert ids == ["1"]


def test_search_properties_property_type_case_insensitive(monkeypatch):
    items = [_search_item(id_=1, types=["Special Purpose"])]
    monkeypatch.setattr(
        _client.requests, "post", lambda *a, **kw: _fake_response(json_data=_search_response(items))
    )

    result = _client.search_properties("church", property_type="special purpose")
    assert result["total_returned"] == 1


def test_search_properties_max_results_cap(monkeypatch):
    items = [_search_item(id_=i) for i in range(20)]
    monkeypatch.setattr(
        _client.requests, "post", lambda *a, **kw: _fake_response(json_data=_search_response(items))
    )

    result = _client.search_properties("church", max_results=5)
    assert result["total_returned"] == 5
    assert len(result["properties"]) == 5


def test_search_properties_filters_none_prices_with_min(monkeypatch):
    items = [
        _search_item(id_=1, asking_price=None),
        _search_item(id_=2, asking_price=500000.0),
    ]
    monkeypatch.setattr(
        _client.requests, "post", lambda *a, **kw: _fake_response(json_data=_search_response(items))
    )

    result = _client.search_properties("church", min_price=100000)
    ids = [p["listing_id"] for p in result["properties"]]
    assert "1" not in ids
    assert "2" in ids


# ---------- get_property_details ----------


def test_get_property_details_by_id(monkeypatch):
    call_urls = []

    def fake_get(url, *args, **kwargs):
        call_urls.append(url)
        if url.endswith("/gallery"):
            return _fake_response(json_data=_gallery_response(1))
        if url.endswith("/brokers"):
            return _fake_response(json_data=_brokers_response())
        return _fake_response(json_data=_asset_detail(id_=1))

    monkeypatch.setattr(_client.requests, "get", fake_get)

    result = _client.get_property_details("1")
    assert result["listing_id"] == "1"
    assert result["url"] == "https://www.crexi.com/properties/tennessee-church-property/1"
    assert result["name"] == "Church Property"
    assert result["city"] == "Nashville"
    assert result["state"] == "TN"
    assert result["price"] == 500000.0
    assert result["property_type"] == "Special Purpose"
    assert "beautiful property" in result["description"]
    assert result["building_sqft"] == 5000
    assert result["lot_acres"] == 1.2
    assert result["year_built"] == "1965"
    assert result["image_urls"] == [
        "https://images.crexi.com/assets/1/img1.jpg",
        "https://images.crexi.com/assets/1/img2.jpg",
    ]
    assert result["broker_names"] == ["John Smith"]


def test_get_property_details_by_url(monkeypatch):
    def fake_get(url, *args, **kwargs):
        if url.endswith("/gallery"):
            return _fake_response(json_data=[])
        if url.endswith("/brokers"):
            return _fake_response(json_data=[])
        return _fake_response(json_data=_asset_detail(id_=12558))

    monkeypatch.setattr(_client.requests, "get", fake_get)

    result = _client.get_property_details(
        "https://www.crexi.com/properties/california-maple-ave/12558"
    )
    assert result["listing_id"] == "12558"


def test_get_property_details_gallery_404_returns_empty_images(monkeypatch):
    def fake_get(url, *args, **kwargs):
        if url.endswith("/gallery"):
            return _fake_response(status=404)
        if url.endswith("/brokers"):
            return _fake_response(json_data=[])
        return _fake_response(json_data=_asset_detail(id_=1))

    monkeypatch.setattr(_client.requests, "get", fake_get)

    result = _client.get_property_details("1")
    assert result["image_urls"] == []


def test_get_property_details_broker_401_returns_none_broker(monkeypatch):
    def fake_get(url, *args, **kwargs):
        if url.endswith("/gallery"):
            return _fake_response(json_data=[])
        if url.endswith("/brokers"):
            return _fake_response(status=401)
        return _fake_response(json_data=_asset_detail(id_=1))

    monkeypatch.setattr(_client.requests, "get", fake_get)

    result = _client.get_property_details("1")
    assert result["broker_names"] == []


def test_get_property_details_broker_request_error_returns_empty(monkeypatch):
    from curl_cffi.requests import RequestsError

    def fake_get(url, *args, **kwargs):
        if url.endswith("/gallery"):
            return _fake_response(json_data=[])
        if url.endswith("/brokers"):
            raise RequestsError("network error")
        return _fake_response(json_data=_asset_detail(id_=1))

    monkeypatch.setattr(_client.requests, "get", fake_get)

    result = _client.get_property_details("1")
    assert result["broker_names"] == []


def test_get_property_details_invalid_id_raises():
    with pytest.raises(ValueError, match="Cannot extract listing ID"):
        _client.get_property_details("not-a-valid-id")


# ---------- MCP tool wrappers ----------


def test_search_properties_tool(monkeypatch):
    items = [_search_item(id_=1)]
    monkeypatch.setattr(
        _client.requests, "post", lambda *a, **kw: _fake_response(json_data=_search_response(items))
    )

    result = asyncio.run(server.search_properties(query="church"))
    assert result["total_returned"] == 1
    assert result["properties"][0]["city"] == "Nashville"


def test_get_property_details_tool(monkeypatch):
    def fake_get(url, *args, **kwargs):
        if url.endswith("/gallery"):
            return _fake_response(json_data=_gallery_response(1))
        if url.endswith("/brokers"):
            return _fake_response(json_data=_brokers_response())
        return _fake_response(json_data=_asset_detail(id_=1))

    monkeypatch.setattr(_client.requests, "get", fake_get)

    result = asyncio.run(server.get_property_details(listing_id_or_url="1"))
    assert result["listing_id"] == "1"
    assert result["broker_names"] == ["John Smith"]
