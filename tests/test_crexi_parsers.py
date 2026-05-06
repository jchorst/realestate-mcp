"""Tests for the Crexi JSON parser functions using hand-crafted fixtures."""

from __future__ import annotations

import pytest

from realestate_mcp.servers.crexi import _client


def _make_search_item(
    *,
    id_: int = 12558,
    name: str = "First Baptist Church",
    types: list[str] | None = None,
    url_slug: str = "texas-first-baptist-church",
    asking_price: float | None = 1250000.0,
    sqft: int | None = 8500,
    locations: list[dict] | None = None,
    thumbnail_url: str | None = "https://images.crexi.com/assets/12558/thumb.jpg",
) -> dict:
    if types is None:
        types = ["Special Purpose"]
    if locations is None:
        locations = [
            {
                "address": "100 Church St",
                "city": "Austin",
                "state": {"code": "TX"},
                "zip": "78701",
                "latitude": 30.267,
                "longitude": -97.743,
            }
        ]
    return {
        "id": id_,
        "name": name,
        "description": "Special Purpose | 8,500 SqFt",
        "thumbnailUrl": thumbnail_url,
        "urlSlug": url_slug,
        "askingPrice": asking_price,
        "squareFootage": sqft,
        "types": types,
        "status": "On-Market",
        "brokerageName": "Faith Realty Group",
        "locations": locations,
        "isNew": False,
    }


def _make_search_payload(items: list[dict]) -> dict:
    return {"data": items, "totalCount": len(items)}


# ---------- _parse_search_result ----------


def test_parse_search_result_basic():
    raw = _make_search_item()
    result = _client._parse_search_result(raw)
    assert result.listing_id == "12558"
    assert result.url == "https://www.crexi.com/properties/texas-first-baptist-church/12558"
    assert result.name == "First Baptist Church"
    assert result.address == "100 Church St"
    assert result.city == "Austin"
    assert result.state == "TX"
    assert result.zip == "78701"
    assert result.price == 1250000.0
    assert result.property_type == "Special Purpose"
    assert result.building_sqft == 8500
    assert result.image_url == "https://images.crexi.com/assets/12558/thumb.jpg"


def test_parse_search_result_multiple_types():
    raw = _make_search_item(types=["Retail", "Special Purpose"])
    result = _client._parse_search_result(raw)
    assert result.property_type == "Retail, Special Purpose"


def test_parse_search_result_no_price():
    raw = _make_search_item(asking_price=None)
    result = _client._parse_search_result(raw)
    assert result.price is None


def test_parse_search_result_no_sqft():
    raw = _make_search_item(sqft=None)
    result = _client._parse_search_result(raw)
    assert result.building_sqft is None


def test_parse_search_result_no_locations():
    raw = _make_search_item(locations=[])
    result = _client._parse_search_result(raw)
    assert result.address == ""
    assert result.city == ""
    assert result.state == ""
    assert result.zip == ""


def test_parse_search_result_missing_id_raises():
    raw = _make_search_item()
    del raw["id"]
    with pytest.raises(RuntimeError, match="Unexpected Crexi response shape"):
        _client._parse_search_result(raw)


# ---------- _parse_search_response ----------


def test_parse_search_response_basic():
    payload = _make_search_payload([_make_search_item(id_=1), _make_search_item(id_=2)])
    results = _client._parse_search_response(payload, max_results=10)
    assert len(results) == 2
    assert results[0].listing_id == "1"
    assert results[1].listing_id == "2"


def test_parse_search_response_respects_max_results():
    items = [_make_search_item(id_=i) for i in range(10)]
    payload = _make_search_payload(items)
    results = _client._parse_search_response(payload, max_results=3)
    assert len(results) == 3


def test_parse_search_response_empty():
    payload = _make_search_payload([])
    results = _client._parse_search_response(payload, max_results=10)
    assert results == []


def test_parse_search_response_missing_data_key_raises():
    with pytest.raises(RuntimeError, match="Unexpected Crexi response shape"):
        _client._parse_search_response({"totalCount": 0}, max_results=10)


def test_parse_search_response_data_not_list_raises():
    with pytest.raises(RuntimeError, match="Unexpected Crexi response shape"):
        _client._parse_search_response({"data": "not a list"}, max_results=10)


# ---------- _parse_asset_detail ----------


def _make_detail_payload(
    *,
    asset_id: str = "12558",
    name: str = "First Baptist Church of Austin",
    types: list[str] | None = None,
    asking_price: float | None = 1250000.0,
    url_slug: str = "texas-first-baptist-church",
    marketing_description: str = "<p>A beautiful historic church in downtown Austin.</p>",
    details: dict | None = None,
    summary_details: list[dict] | None = None,
    locations: list[dict] | None = None,
) -> dict:
    if types is None:
        types = ["Special Purpose"]
    if details is None:
        details = {
            "Asking Price": "$1,250,000",
            "Property Type": "Special Purpose",
            "Year Built": "1950",
            "Lot Size (acres)": "0.75",
            "Square Footage": "8,500",
        }
    if summary_details is None:
        summary_details = [
            {"key": "SquareFootage", "value": 8500, "display": "8,500"},
            {"key": "AskingPrice", "value": 1250000.0, "display": "$1,250,000"},
            {"key": "YearBuilt", "value": "1950", "display": "1950"},
        ]
    if locations is None:
        locations = [
            {
                "address": "100 Church St",
                "city": "Austin",
                "county": "Travis",
                "state": {"code": "TX", "name": "Texas"},
                "zip": "78701",
                "latitude": 30.267,
                "longitude": -97.743,
            }
        ]
    return {
        "id": int(asset_id),
        "name": name,
        "description": "Special Purpose | 8,500 SqFt",
        "marketingDescription": marketing_description,
        "types": types,
        "status": "Active",
        "urlSlug": url_slug,
        "askingPrice": asking_price,
        "thumbnailUrl": "https://images.crexi.com/assets/12558/thumb.jpg",
        "details": details,
        "summaryDetails": summary_details,
        "locations": locations,
        "isUnpriced": False,
        "hasBrokerOfRecord": False,
        "brokerProducts": [],
    }


def test_parse_asset_detail_basic():
    payload = _make_detail_payload()
    detail = _client._parse_asset_detail(payload, "12558")
    assert detail.listing_id == "12558"
    assert detail.url == "https://www.crexi.com/properties/texas-first-baptist-church/12558"
    assert detail.name == "First Baptist Church of Austin"
    assert detail.address == "100 Church St"
    assert detail.city == "Austin"
    assert detail.state == "TX"
    assert detail.zip == "78701"
    assert detail.price == 1250000.0
    assert detail.property_type == "Special Purpose"
    assert "beautiful historic church" in detail.description
    assert detail.building_sqft == 8500
    assert detail.lot_acres == 0.75
    assert detail.year_built == "1950"
    assert detail.image_urls == []
    assert detail.broker_names == []


def test_parse_asset_detail_strips_html_from_description():
    payload = _make_detail_payload(
        marketing_description="<p>Great <strong>location</strong>!</p>"
    )
    detail = _client._parse_asset_detail(payload, "12558")
    assert "<p>" not in detail.description
    assert "<strong>" not in detail.description
    assert "Great" in detail.description
    assert "location" in detail.description


def test_parse_asset_detail_falls_back_to_description_field():
    payload = _make_detail_payload(marketing_description="")
    payload["description"] = "Special Purpose | 8,500 SqFt"
    detail = _client._parse_asset_detail(payload, "12558")
    assert "Special Purpose" in detail.description


def test_parse_asset_detail_no_price():
    payload = _make_detail_payload(asking_price=None)
    detail = _client._parse_asset_detail(payload, "12558")
    assert detail.price is None


def test_parse_asset_detail_sqft_from_details_dict():
    payload = _make_detail_payload(summary_details=[])
    detail = _client._parse_asset_detail(payload, "12558")
    assert detail.building_sqft == 8500


def test_parse_asset_detail_multiple_types():
    payload = _make_detail_payload(types=["Office", "Special Purpose"])
    detail = _client._parse_asset_detail(payload, "12558")
    assert detail.property_type == "Office, Special Purpose"


def test_parse_asset_detail_no_locations():
    payload = _make_detail_payload(locations=[])
    detail = _client._parse_asset_detail(payload, "12558")
    assert detail.address == ""
    assert detail.city == ""
    assert detail.state == ""
    assert detail.zip == ""


def test_parse_asset_detail_non_dict_raises():
    with pytest.raises(RuntimeError, match="Unexpected Crexi response shape"):
        _client._parse_asset_detail([], "12558")
