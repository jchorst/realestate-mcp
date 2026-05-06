"""End-to-end tests for the Redfin client with mocked HTTP."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from realestate_mcp.servers.redfin import _client, server

# ---------------------------------------------------------------------------
# HTML builders
# ---------------------------------------------------------------------------


def _encode_cache_entry(payload: dict) -> dict:
    text = "{}&&" + json.dumps({"payload": payload})
    return {"res": {"text": text}, "loaded": True}


def _gis_payload(homes: list[dict]) -> dict:
    return {"homes": homes, "dataSources": [], "buildings": []}


def _home_dict(
    *,
    property_id: int = 111190110,
    listing_id: int = 214646754,
    mls_id: str = "4366321",
    data_source_id: int = 103,
    beds: int = 3,
    baths: float = 2.0,
    price: int = 400000,
    sqft: int = 1800,
    lot_sqft: int = 8000,
    year_built: int = 1990,
    city: str = "Arden",
    state: str = "NC",
    zip_code: str = "28704",
    url: str = "/NC/Arden/732-Streamside-Dr-28704/home/111190110",
    dom: int = 5,
) -> dict:
    return {
        "propertyId": property_id,
        "listingId": listing_id,
        "mlsId": {"value": mls_id, "label": "MLS#"},
        "dataSourceId": data_source_id,
        "photoFormat": "webp",
        "beds": beds,
        "baths": baths,
        "price": {"value": price, "level": 1},
        "sqFt": {"value": sqft, "level": 1},
        "lotSize": {"value": lot_sqft, "level": 1},
        "yearBuilt": {"value": year_built, "level": 1},
        "city": city,
        "state": state,
        "zip": zip_code,
        "url": url,
        "streetLine": {"value": "732 Streamside Dr", "level": 1},
        "unitNumber": {"level": 1},
        "dom": {"value": dom, "level": 1},
        "hoa": {"level": 1},
        "isHoaFrequencyKnown": False,
    }


def _atf_payload(
    *,
    beds: int = 3,
    baths: float = 2.0,
    price: int = 400000,
    sqft: int = 1800,
    lot_sqft: int = 8000,
    year_built: int = 1990,
    dom: int = 5,
) -> dict:
    return {
        "addressSectionInfo": {
            "beds": beds,
            "baths": baths,
            "priceInfo": {
                "amount": price,
                "label": "Price",
                "displayLevel": 1,
                "dataSourceId": 103,
            },
            "sqFt": {"value": sqft, "displayLevel": 1},
            "lotSize": lot_sqft,
            "yearBuilt": year_built,
            "streetAddress": {"assembledAddress": "732 Streamside Dr"},
            "city": "Arden",
            "state": "NC",
            "zip": "28704",
            "cumulativeDaysOnMarket": dom,
            "url": "/NC/Arden/732-Streamside-Dr-28704/home/111190110",
        },
        "mediaBrowserInfo": {
            "photos": [
                {"photoUrls": {"fullScreenPhotoUrl": "https://cdn.example/photo/1.jpg"}},
                {"photoUrls": {"fullScreenPhotoUrl": "https://cdn.example/photo/2.jpg"}},
            ]
        },
    }


def _mhip_payload() -> dict:
    return {
        "mainHouseInfo": {
            "listingId": 214646754,
            "listingAgents": [
                {
                    "agentInfo": {"agentName": "Agent Smith", "isRedfinAgent": False},
                    "brokerName": "Big Realty Co",
                }
            ],
        },
        "openHouseInfo": {},
    }


def _build_search_html(homes: list[dict]) -> str:
    cache = {
        "/stingray/api/gis?region_id=11730&region_type=2": _encode_cache_entry(
            _gis_payload(homes)
        )
    }
    rss = {"ReactServerAgent.cache": {"dataCache": cache}}
    rss_json = json.dumps(rss)
    return (
        f"root.__reactServerState.InitialContext = {rss_json};\n"
        "root.__reactServerState.Config = {};"
    )


def _build_detail_html(
    listing_id: str = "111190110",
    description: str = "A fine property.",
    **atf_kwargs: Any,
) -> str:
    ld = json.dumps(
        {
            "@context": "https://schema.org",
            "@type": ["Product", "RealEstateListing"],
            "name": "732 Streamside Dr",
            "description": description,
            "url": f"https://www.redfin.com/NC/Arden/732-Streamside-Dr-28704/home/{listing_id}",
            "offers": {"@type": "Offer", "price": 400000, "priceCurrency": "USD"},
        }
    )
    cache = {
        "/stingray/api/home/details/aboveTheFold": _encode_cache_entry(
            _atf_payload(**atf_kwargs)
        ),
        "/stingray/api/home/details/mainHouseInfoPanelInfo": _encode_cache_entry(
            _mhip_payload()
        ),
    }
    rss = {"ReactServerAgent.cache": {"dataCache": cache}}
    rss_json = json.dumps(rss)
    return (
        f"root.__reactServerState.InitialContext = {rss_json};\n"
        f"root.__reactServerState.Config = {{}};\n"
        f'<script type="application/ld+json">{ld}</script>'
    )


def _fake_response(html: str = "", status: int = 200) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.raise_for_status = MagicMock()
    r.text = html
    return r


# ---------------------------------------------------------------------------
# search_homes
# ---------------------------------------------------------------------------


def test_search_homes_basic(monkeypatch):
    homes = [_home_dict(property_id=1, price=400000), _home_dict(property_id=2, price=500000)]
    html = _build_search_html(homes)

    monkeypatch.setattr(_client.requests, "get", lambda *a, **kw: _fake_response(html))

    result = _client.search_homes("28704")
    assert result["search_area"] == "ZIP 28704"
    assert result["total_returned"] == 2
    assert len(result["homes"]) == 2


def test_search_homes_max_results(monkeypatch):
    homes = [_home_dict(property_id=i, url=f"/NC/Arden/Addr/home/{i}") for i in range(10)]
    html = _build_search_html(homes)

    monkeypatch.setattr(_client.requests, "get", lambda *a, **kw: _fake_response(html))

    result = _client.search_homes("28704", max_results=3)
    assert result["total_returned"] == 3
    assert len(result["homes"]) == 3


def test_search_homes_min_beds_filter(monkeypatch):
    homes = [
        _home_dict(property_id=1, beds=2, url="/NC/A/A/home/1"),
        _home_dict(property_id=2, beds=4, url="/NC/A/A/home/2"),
        _home_dict(property_id=3, beds=3, url="/NC/A/A/home/3"),
    ]
    html = _build_search_html(homes)
    monkeypatch.setattr(_client.requests, "get", lambda *a, **kw: _fake_response(html))

    result = _client.search_homes("28704", min_beds=3)
    ids = [h["listing_id"] for h in result["homes"]]
    assert "1" not in ids
    assert "2" in ids
    assert "3" in ids


def test_search_homes_max_beds_filter(monkeypatch):
    homes = [
        _home_dict(property_id=1, beds=2, url="/NC/A/A/home/1"),
        _home_dict(property_id=2, beds=5, url="/NC/A/A/home/2"),
    ]
    html = _build_search_html(homes)
    monkeypatch.setattr(_client.requests, "get", lambda *a, **kw: _fake_response(html))

    result = _client.search_homes("28704", max_beds=3)
    ids = [h["listing_id"] for h in result["homes"]]
    assert "1" in ids
    assert "2" not in ids


def test_search_homes_price_filter(monkeypatch):
    homes = [
        _home_dict(property_id=1, price=200000, url="/NC/A/A/home/1"),
        _home_dict(property_id=2, price=500000, url="/NC/A/A/home/2"),
        _home_dict(property_id=3, price=800000, url="/NC/A/A/home/3"),
    ]
    html = _build_search_html(homes)
    monkeypatch.setattr(_client.requests, "get", lambda *a, **kw: _fake_response(html))

    result = _client.search_homes("28704", min_price=300000, max_price=600000)
    ids = [h["listing_id"] for h in result["homes"]]
    assert "1" not in ids
    assert "2" in ids
    assert "3" not in ids


def test_search_homes_raises_on_missing_gis_cache(monkeypatch):
    cache = {"some/other": _encode_cache_entry({"data": "stuff"})}
    rss = {"ReactServerAgent.cache": {"dataCache": cache}}
    rss_json = json.dumps(rss)
    html = (
        f"root.__reactServerState.InitialContext = {rss_json};\n"
        "root.__reactServerState.Config = {};"
    )

    monkeypatch.setattr(_client.requests, "get", lambda *a, **kw: _fake_response(html))

    with pytest.raises(RuntimeError, match="Unexpected Redfin response shape"):
        _client.search_homes("28704")


def test_search_homes_raises_on_missing_rss_marker(monkeypatch):
    monkeypatch.setattr(
        _client.requests, "get", lambda *a, **kw: _fake_response("<html>no state</html>")
    )
    with pytest.raises(RuntimeError, match="Unexpected Redfin response shape"):
        _client.search_homes("28704")


def test_search_homes_returns_image_url(monkeypatch):
    homes = [_home_dict(property_id=1, mls_id="4366321", data_source_id=103)]
    html = _build_search_html(homes)
    monkeypatch.setattr(_client.requests, "get", lambda *a, **kw: _fake_response(html))

    result = _client.search_homes("28704")
    assert result["homes"][0]["image_url"] == "https://ssl.cdn-redfin.com/photo/103/bigphoto/321/4366321_0.webp"


# ---------------------------------------------------------------------------
# get_home_details
# ---------------------------------------------------------------------------


def test_get_home_details_by_full_url(monkeypatch):
    html = _build_detail_html(description="Great home near mountains.")
    monkeypatch.setattr(_client.requests, "get", lambda *a, **kw: _fake_response(html))

    result = _client.get_home_details(
        "https://www.redfin.com/NC/Arden/732-Streamside-Dr-28704/home/111190110"
    )
    assert result["listing_id"] == "111190110"
    assert result["address"] == "732 Streamside Dr"
    assert result["price"] == 400000.0
    assert result["bedrooms"] == 3
    assert result["bathrooms"] == 2.0
    assert result["description"] == "Great home near mountains."
    assert result["listing_agent"] == "Agent Smith"
    assert result["listing_brokerage"] == "Big Realty Co"
    assert result["hoa_fee"] is None


def test_get_home_details_by_numeric_string_id(monkeypatch):
    html = _build_detail_html()
    monkeypatch.setattr(_client.requests, "get", lambda *a, **kw: _fake_response(html))

    result = _client.get_home_details("111190110")
    assert result["listing_id"] == "111190110"


def test_get_home_details_by_int_id(monkeypatch):
    """Regression: int IDs must work (not just strings)."""
    html = _build_detail_html()
    monkeypatch.setattr(_client.requests, "get", lambda *a, **kw: _fake_response(html))

    result = _client.get_home_details(111190110)
    assert result["listing_id"] == "111190110"


def test_get_home_details_image_urls(monkeypatch):
    html = _build_detail_html()
    monkeypatch.setattr(_client.requests, "get", lambda *a, **kw: _fake_response(html))

    result = _client.get_home_details("111190110")
    assert result["image_urls"] == [
        "https://cdn.example/photo/1.jpg",
        "https://cdn.example/photo/2.jpg",
    ]


def test_get_home_details_days_on_market(monkeypatch):
    html = _build_detail_html(dom=12)
    monkeypatch.setattr(_client.requests, "get", lambda *a, **kw: _fake_response(html))

    result = _client.get_home_details("111190110")
    assert result["days_on_market"] == 12


def test_get_home_details_raises_on_bad_id():
    with pytest.raises(ValueError, match="Cannot extract Redfin listing ID"):
        _client.get_home_details("not-a-valid-id")


def test_get_home_details_raises_on_missing_atf(monkeypatch):
    cache: dict = {}
    rss = {"ReactServerAgent.cache": {"dataCache": cache}}
    html = f"root.__reactServerState.InitialContext = {json.dumps(rss)};\n"
    monkeypatch.setattr(_client.requests, "get", lambda *a, **kw: _fake_response(html))

    with pytest.raises(RuntimeError, match="Unexpected Redfin response shape"):
        _client.get_home_details("111190110")


def test_get_home_details_url_from_cache_used(monkeypatch):
    """The URL passed in is persisted to the result."""
    full_url = "https://www.redfin.com/NC/Arden/732-Streamside-Dr-28704/home/111190110"
    html = _build_detail_html()
    captured_urls = []

    def fake_get(url, *args, **kwargs):
        captured_urls.append(url)
        return _fake_response(html)

    monkeypatch.setattr(_client.requests, "get", fake_get)
    result = _client.get_home_details(full_url)
    assert captured_urls[0] == full_url
    assert result["url"] == full_url


# ---------------------------------------------------------------------------
# MCP tool wrappers (async)
# ---------------------------------------------------------------------------


def test_mcp_search_homes_async(monkeypatch):
    homes = [_home_dict(property_id=1)]
    html = _build_search_html(homes)
    monkeypatch.setattr(_client.requests, "get", lambda *a, **kw: _fake_response(html))

    result = asyncio.run(server.search_homes("28704"))
    assert result["total_returned"] == 1


def test_mcp_get_home_details_async(monkeypatch):
    html = _build_detail_html()
    monkeypatch.setattr(_client.requests, "get", lambda *a, **kw: _fake_response(html))

    result = asyncio.run(server.get_home_details("111190110"))
    assert result["listing_id"] == "111190110"
