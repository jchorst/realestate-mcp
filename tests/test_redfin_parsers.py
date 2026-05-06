"""Tests for Redfin JSON parsers with hand-crafted minimal fixtures."""

from __future__ import annotations

import json

import pytest

from realestate_mcp.servers.redfin import _client

# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _make_rss_html(cache: dict) -> str:
    """Wrap a dataCache dict in the HTML structure the parser expects."""
    rss = {"ReactServerAgent.cache": {"dataCache": cache}}
    payload = json.dumps(rss)
    return (
        f"root.__reactServerState.InitialContext = {payload};\n"
        "root.__reactServerState.Config = {};"
    )


def _encode_cache_entry(payload: dict) -> dict:
    """Encode a payload dict as a cache entry with '{}&&' prefix."""
    text = "{}&&" + json.dumps({"payload": payload})
    return {"res": {"text": text}, "loaded": True}


def _gis_payload(homes: list[dict]) -> dict:
    return {"homes": homes, "dataSources": [], "buildings": []}


def _home(
    *,
    property_id: int = 111190110,
    listing_id: int = 214646754,
    mls_id: str = "4366321",
    data_source_id: int = 103,
    photo_format: str = "webp",
    beds: int = 4,
    baths: float = 3.5,
    price: int = 1600000,
    sqft: int = 3527,
    lot_sqft: int = 47044,
    year_built: int = 2014,
    city: str = "Arden",
    state: str = "NC",
    zip_code: str = "28704",
    url: str = "/NC/Arden/732-Streamside-Dr-28704/home/111190110",
    dom: int = 1,
    hoa: int | None = 123,
) -> dict:
    entry: dict = {
        "propertyId": property_id,
        "listingId": listing_id,
        "mlsId": {"value": mls_id, "label": "MLS#"},
        "dataSourceId": data_source_id,
        "photoFormat": photo_format,
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
        "hoa": {"value": hoa, "level": 1} if hoa is not None else {"level": 1},
        "isHoaFrequencyKnown": hoa is not None,
    }
    return entry


def _atf_payload(
    *,
    beds: int = 4,
    baths: float = 3.5,
    price: int = 1600000,
    sqft: int = 3527,
    lot_sqft: int = 47044,
    year_built: int = 2014,
    address: str = "732 Streamside Dr",
    city: str = "Arden",
    state: str = "NC",
    zip_code: str = "28704",
    dom: int = 0,
    photos: list[dict] | None = None,
) -> dict:
    if photos is None:
        photos = [
            {
                "photoUrls": {
                    "fullScreenPhotoUrl": "https://ssl.cdn-redfin.com/photo/103/bigphoto/321/4366321_0.jpg",
                    "nonFullScreenPhotoUrl": "https://ssl.cdn-redfin.com/photo/103/mbpaddedwide/321/genMid.4366321_0.jpg",
                }
            }
        ]
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
            "streetAddress": {
                "assembledAddress": address,
                "streetNumber": "732",
                "streetName": "Streamside",
                "streetType": "Dr",
            },
            "city": city,
            "state": state,
            "zip": zip_code,
            "cumulativeDaysOnMarket": dom,
            "url": "/NC/Arden/732-Streamside-Dr-28704/home/111190110",
        },
        "mediaBrowserInfo": {"photos": photos},
    }


def _mhip_payload(
    agent_name: str = "Karen Woodard",
    broker_name: str = "Howard Hanna Beverly-Hanks",
) -> dict:
    return {
        "mainHouseInfo": {
            "listingId": 214646754,
            "listingAgents": [
                {
                    "agentInfo": {"agentName": agent_name, "isRedfinAgent": False},
                    "brokerName": broker_name,
                }
            ],
        },
        "openHouseInfo": {},
    }


def _detail_html(description: str = "A fine home.") -> str:
    ld = {
        "@context": "https://schema.org",
        "@type": ["Product", "RealEstateListing"],
        "name": "732 Streamside Dr",
        "description": description,
        "url": "https://www.redfin.com/NC/Arden/732-Streamside-Dr-28704/home/111190110",
        "offers": {"@type": "Offer", "price": 1600000, "priceCurrency": "USD"},
    }
    return f'<script type="application/ld+json">{json.dumps(ld)}</script>'


# ---------------------------------------------------------------------------
# _parse_search_results
# ---------------------------------------------------------------------------


def test_parse_search_results_basic():
    cache = {
        "/stingray/api/gis?region_id=11730": _encode_cache_entry(_gis_payload([_home()]))
    }
    results = _client._parse_search_results(cache)
    assert len(results) == 1
    h = results[0]
    assert h.listing_id == "111190110"
    assert h.url == "https://www.redfin.com/NC/Arden/732-Streamside-Dr-28704/home/111190110"
    assert h.address == "732 Streamside Dr"
    assert h.city == "Arden"
    assert h.state == "NC"
    assert h.zip == "28704"
    assert h.price == 1600000.0
    assert h.bedrooms == 4
    assert h.bathrooms == 3.5
    assert h.building_sqft == 3527
    assert h.lot_sqft == 47044
    assert h.year_built == 2014
    assert h.image_url == "https://ssl.cdn-redfin.com/photo/103/bigphoto/321/4366321_0.webp"


def test_parse_search_results_missing_gis_key_raises():
    cache = {"some/other/key": _encode_cache_entry({"data": "stuff"})}
    with pytest.raises(RuntimeError, match="Unexpected Redfin response shape"):
        _client._parse_search_results(cache)


def test_parse_search_results_homes_not_list_raises():
    cache = {
        "/stingray/api/gis?x": _encode_cache_entry({"homes": "not-a-list"})
    }
    with pytest.raises(RuntimeError, match="Unexpected Redfin response shape"):
        _client._parse_search_results(cache)


def test_parse_search_results_skips_entry_without_id():
    bad = _home()
    bad["propertyId"] = None
    bad["listingId"] = None
    bad["url"] = "/NC/Arden/no-home-segment"
    good = _home(property_id=999, url="/NC/Arden/Some-St-28704/home/999")
    cache = {
        "/stingray/api/gis?x": _encode_cache_entry(_gis_payload([bad, good]))
    }
    results = _client._parse_search_results(cache)
    assert len(results) == 1
    assert results[0].listing_id == "999"


def test_parse_search_results_optional_fields_none_safe():
    h = _home()
    del h["beds"]
    del h["baths"]
    del h["yearBuilt"]
    del h["lotSize"]
    cache = {"/stingray/api/gis?x": _encode_cache_entry(_gis_payload([h]))}
    results = _client._parse_search_results(cache)
    r = results[0]
    assert r.bedrooms is None
    assert r.bathrooms is None
    assert r.year_built is None
    assert r.lot_sqft is None


def test_parse_search_results_half_bath():
    cache = {
        "/stingray/api/gis?x": _encode_cache_entry(_gis_payload([_home(baths=1.5)]))
    }
    results = _client._parse_search_results(cache)
    assert results[0].bathrooms == 1.5


def test_parse_search_results_unit_number_included_in_address():
    h = _home()
    h["unitNumber"] = {"value": "Apt 2B", "level": 1}
    cache = {"/stingray/api/gis?x": _encode_cache_entry(_gis_payload([h]))}
    results = _client._parse_search_results(cache)
    assert results[0].address == "732 Streamside Dr Apt 2B"


# ---------------------------------------------------------------------------
# _parse_home_details
# ---------------------------------------------------------------------------


def test_parse_home_details_basic():
    cache = {
        "/stingray/api/home/details/aboveTheFold": _encode_cache_entry(_atf_payload()),
        "/stingray/api/home/details/mainHouseInfoPanelInfo": _encode_cache_entry(_mhip_payload()),
    }
    html = _detail_html("A lovely mountain home.")
    detail_url = "https://www.redfin.com/NC/Arden/732-Streamside-Dr-28704/home/111190110"
    details = _client._parse_home_details(cache, html, "111190110", detail_url)
    assert details.listing_id == "111190110"
    assert details.url == "https://www.redfin.com/NC/Arden/732-Streamside-Dr-28704/home/111190110"
    assert details.address == "732 Streamside Dr"
    assert details.city == "Arden"
    assert details.state == "NC"
    assert details.zip == "28704"
    assert details.price == 1600000.0
    assert details.bedrooms == 4
    assert details.bathrooms == 3.5
    assert details.building_sqft == 3527
    assert details.lot_sqft == 47044
    assert details.year_built == 2014
    assert details.description == "A lovely mountain home."
    assert len(details.image_urls) == 1
    assert details.image_urls[0] == "https://ssl.cdn-redfin.com/photo/103/bigphoto/321/4366321_0.jpg"
    assert details.listing_agent == "Karen Woodard"
    assert details.listing_brokerage == "Howard Hanna Beverly-Hanks"
    assert details.hoa_fee is None  # always None in MVP


def test_parse_home_details_multiple_photos_deduplicated():
    photos = [
        {"photoUrls": {"fullScreenPhotoUrl": "https://cdn/photo/1.jpg"}},
        {"photoUrls": {"fullScreenPhotoUrl": "https://cdn/photo/2.jpg"}},
        {"photoUrls": {"fullScreenPhotoUrl": "https://cdn/photo/1.jpg"}},  # dup
    ]
    cache = {
        "/stingray/api/home/details/aboveTheFold": _encode_cache_entry(_atf_payload(photos=photos)),
        "/stingray/api/home/details/mainHouseInfoPanelInfo": _encode_cache_entry(_mhip_payload()),
    }
    details = _client._parse_home_details(cache, "", "111190110", "https://www.redfin.com/home/111190110")
    assert details.image_urls == ["https://cdn/photo/1.jpg", "https://cdn/photo/2.jpg"]


def test_parse_home_details_missing_atf_raises():
    cache = {}
    with pytest.raises(RuntimeError, match="Unexpected Redfin response shape"):
        _client._parse_home_details(cache, "", "111190110", "https://x.com")


def test_parse_home_details_optional_agent_absent():
    cache = {
        "/stingray/api/home/details/aboveTheFold": _encode_cache_entry(_atf_payload()),
        # No mainHouseInfoPanelInfo
    }
    details = _client._parse_home_details(cache, _detail_html(), "111190110", "https://x.com")
    assert details.listing_agent is None
    assert details.listing_brokerage is None


def test_parse_home_details_days_on_market():
    cache = {
        "/stingray/api/home/details/aboveTheFold": _encode_cache_entry(_atf_payload(dom=14)),
    }
    details = _client._parse_home_details(cache, "", "111190110", "https://x.com")
    assert details.days_on_market == 14


def test_parse_home_details_no_description_returns_none():
    cache = {
        "/stingray/api/home/details/aboveTheFold": _encode_cache_entry(_atf_payload()),
    }
    details = _client._parse_home_details(cache, "<html>no ld+json here</html>", "111190110", "https://x.com")
    assert details.description is None


# ---------------------------------------------------------------------------
# _decode_cache_entry
# ---------------------------------------------------------------------------


def test_decode_cache_entry_strips_prefix():
    entry = {"res": {"text": '{}&&{"payload": {"key": "val"}}'}}
    result = _client._decode_cache_entry(entry)
    assert result == {"key": "val"}


def test_decode_cache_entry_handles_no_prefix():
    entry = {"res": {"text": '{"payload": {"key": "val"}}'}}
    result = _client._decode_cache_entry(entry)
    assert result == {"key": "val"}


def test_decode_cache_entry_returns_none_on_bad_json():
    entry = {"res": {"text": "{}&&not-json"}}
    assert _client._decode_cache_entry(entry) is None


def test_decode_cache_entry_returns_none_for_empty():
    assert _client._decode_cache_entry({"res": {"text": ""}}) is None
    assert _client._decode_cache_entry({"res": {}}) is None
    assert _client._decode_cache_entry({}) is None
