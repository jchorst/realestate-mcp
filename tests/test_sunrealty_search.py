# ruff: noqa: E501
"""End-to-end integration tests for the Sun Realty client with mocked HTTP."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from realestate_mcp.servers.sunrealty import _client, server

# ---------- HTTP mock helpers ----------


def _fake_response(json_data: Any = None, text: str = "", status: int = 200) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.raise_for_status = MagicMock()
    r.json = MagicMock(return_value=json_data)
    r.text = text if text else (json.dumps(json_data) if json_data else "")
    return r


# ---------- Fixture builders ----------


def _solr_doc(
    item_id: str = "1",
    beds: int = 4,
    baths: float = 2.0,
    town: str = "Duck",
) -> dict:
    return {
        "item_id": item_id,
        "is_eid": item_id,
        "ss_name": f"House {item_id}",
        "ss_url": f"https://www.sunrealtync.com/outer-banks/duck-nc-rentals/oceanfront/{item_id}",
        "is_nid$field_beds": beds,
        "fs_rc_core_lodging_product$baths": baths,
        "is_rc_core_lodging_product$occ_total": beds * 2,
        "sm_nid$rc_core_term_town$name": [town],
        "sm_nid$rc_core_term_community$name": ["Pine Island"],
        "sm_nid$rc_core_term_distance_to_beach$name": ["Oceanside"],
        "sm_nid$rc_core_term_featured_amenities$name": ["WiFi"],
        "sm_rc_core_item_teaser_slideshow": ["https://images.rezfusion.com?source=img.jpg"],
        "ss_vrweb_default_image": "https://images.rezfusion.com?source=img.jpg",
    }


def _solr_payload(docs: list[dict]) -> dict:
    return {"response": {"numFound": len(docs), "start": 0, "docs": docs}}


def _solr_resolve_payload(url: str) -> dict:
    return {"response": {"numFound": 1, "start": 0, "docs": [{"ss_url": url}]}}


_DETAIL_HTML = """<!DOCTYPE html>
<html><body>
<div class="field field-name-title">Blue Whale SWB-36</div>
<div class="rc-lodging-beds rc-lodging-detail">Bedrooms: 4</div>
<div class="rc-lodging-baths rc-lodging-detail">Bathrooms: 3 &amp; 1 Half</div>
<div class="field field-name-field-town">Duck</div>
<div class="field field-name-rc-core-term-community">Pine Island</div>
<div class="field field-name-body">A beautiful oceanfront home with stunning views and luxury amenities.</div>
<div class="group-vr-full-amenities group-vr-property-amenities field-group-foundation_group_section_item">
  <h3>Amenities &amp; Beds</h3>
  <div class="item-list"><ul><li>Ocean view</li><li>Private Pool</li></ul></div>
</div>
<img src="https://images.rezfusion.com?source=img1.jpg" />
<img src="https://images.rezfusion.com?source=img2.jpg" />
<script>
jQuery.extend(Drupal.settings, {"rcItemAvailForm": [{"eid": "655", "avail":
  [{"b": "2026-06-21", "e": "2026-08-22", "a": "1", "q": "1", "s": "1", "x": ""}]}]});
</script>
</body></html>"""


# ---------- search_rentals ----------


def test_search_rentals_returns_all_listings(monkeypatch):
    docs = [_solr_doc(str(i)) for i in range(5)]
    monkeypatch.setattr(
        _client.requests, "get", lambda *a, **kw: _fake_response(_solr_payload(docs))
    )
    result = _client.search_rentals("duck")
    assert result["total_returned"] == 5
    assert len(result["listings"]) == 5


def test_search_rentals_min_bedrooms_filter(monkeypatch):
    docs = [
        _solr_doc("small", beds=3),
        _solr_doc("medium", beds=5),
        _solr_doc("large", beds=8),
    ]
    monkeypatch.setattr(
        _client.requests, "get", lambda *a, **kw: _fake_response(_solr_payload(docs))
    )
    result = _client.search_rentals("duck", min_bedrooms=5)
    ids = [li["listing_id"] for li in result["listings"]]
    assert "small" not in ids
    assert "medium" in ids
    assert "large" in ids


def test_search_rentals_max_results_cap(monkeypatch):
    docs = [_solr_doc(str(i)) for i in range(20)]
    monkeypatch.setattr(
        _client.requests, "get", lambda *a, **kw: _fake_response(_solr_payload(docs))
    )
    result = _client.search_rentals("duck", max_results=5)
    assert result["total_returned"] == 5
    assert len(result["listings"]) == 5


def test_search_rentals_town_name_in_solr_fq(monkeypatch):
    captured_params = []

    def fake_get(url, *args, **kwargs):
        captured_params.append(kwargs.get("params", {}))
        return _fake_response(_solr_payload([]))

    monkeypatch.setattr(_client.requests, "get", fake_get)
    _client.search_rentals("duck")

    assert captured_params
    fq = captured_params[0].get("fq", "")
    assert "Duck" in fq


def test_search_rentals_corolla_town_name(monkeypatch):
    captured_params = []

    def fake_get(url, *args, **kwargs):
        captured_params.append(kwargs.get("params", {}))
        return _fake_response(_solr_payload([]))

    monkeypatch.setattr(_client.requests, "get", fake_get)
    _client.search_rentals("corolla")

    fq = captured_params[0].get("fq", "")
    assert "Corolla" in fq


def test_search_rentals_carova_alias(monkeypatch):
    captured_params = []

    def fake_get(url, *args, **kwargs):
        captured_params.append(kwargs.get("params", {}))
        return _fake_response(_solr_payload([]))

    monkeypatch.setattr(_client.requests, "get", fake_get)

    _client.search_rentals("carova")
    _client.search_rentals("4x4")

    assert "Carova" in captured_params[0].get("fq", "")
    assert "Carova" in captured_params[1].get("fq", "")


def test_search_rentals_raises_on_unknown_town():
    with pytest.raises(ValueError, match="Unknown town"):
        _client.search_rentals("bermuda")


def test_search_rentals_raises_on_schema_drift(monkeypatch):
    monkeypatch.setattr(
        _client.requests, "get", lambda *a, **kw: _fake_response({"bad": "shape"})
    )
    with pytest.raises(RuntimeError, match="Unexpected Sun Realty response shape"):
        _client.search_rentals("duck")


def test_search_rentals_check_in_on_listings(monkeypatch):
    docs = [_solr_doc("1")]
    monkeypatch.setattr(
        _client.requests, "get", lambda *a, **kw: _fake_response(_solr_payload(docs))
    )
    result = _client.search_rentals("duck", check_in="2026-06-21")
    assert result["listings"][0]["check_in"] == "2026-06-21"


def test_search_rentals_listing_fields(monkeypatch):
    docs = [_solr_doc("655", beds=4, baths=3.0)]
    monkeypatch.setattr(
        _client.requests, "get", lambda *a, **kw: _fake_response(_solr_payload(docs))
    )
    result = _client.search_rentals("duck")
    li = result["listings"][0]
    assert li["listing_id"] == "655"
    assert li["bedrooms"] == 4
    assert li["bathrooms_full"] == 3
    assert li["bathrooms_half"] == 0
    assert li["sleeps"] == 8
    assert li["town"] == "Duck"
    assert li["community"] == "Pine Island"
    assert "rezfusion" in (li["image_url"] or "")


def test_search_rentals_search_area_in_response(monkeypatch):
    monkeypatch.setattr(
        _client.requests, "get", lambda *a, **kw: _fake_response(_solr_payload([]))
    )
    result = _client.search_rentals("duck")
    assert "Duck" in result["search_area"]
    assert "Sun Realty" in result["search_area"]


# ---------- get_rental_details ----------


def _make_detail_fake_get(
    *, resolve_payload: dict | None = None, html: str = _DETAIL_HTML
):
    """Return a fake_get that routes Solr resolve calls to JSON and detail page to HTML."""
    call_count = {"n": 0}

    def fake_get(url, *args, **kwargs):
        call_count["n"] += 1
        if "solr" in url:
            return _fake_response(resolve_payload or _solr_resolve_payload(
                "https://www.sunrealtync.com/outer-banks/duck-nc-rentals/oceanfront/655"
            ))
        return _fake_response(text=html)

    return fake_get


def test_get_rental_details_by_numeric_id(monkeypatch):
    calls = []

    def fake_get(url, *args, **kwargs):
        calls.append(url)
        if "solr" in url:
            return _fake_response(_solr_resolve_payload(
                "https://www.sunrealtync.com/outer-banks/duck-nc-rentals/oceanfront/655"
            ))
        return _fake_response(text=_DETAIL_HTML)

    monkeypatch.setattr(_client.requests, "get", fake_get)
    d = _client.get_rental_details("655")
    assert d["bedrooms"] == 4
    assert d["bathrooms_full"] == 3
    assert d["bathrooms_half"] == 1
    # First call is Solr resolve, second is detail page
    assert any("solr" in url for url in calls)


def test_get_rental_details_by_int(monkeypatch):
    def fake_get(url, *args, **kwargs):
        if "solr" in url:
            return _fake_response(_solr_resolve_payload(
                "https://www.sunrealtync.com/outer-banks/duck-nc-rentals/oceanfront/655"
            ))
        return _fake_response(text=_DETAIL_HTML)

    monkeypatch.setattr(_client.requests, "get", fake_get)
    d = _client.get_rental_details(655)
    assert d["bedrooms"] == 4


def test_get_rental_details_by_property_code(monkeypatch):
    calls = []

    def fake_get(url, *args, **kwargs):
        calls.append(url)
        if "solr" in url:
            return _fake_response(_solr_resolve_payload(
                "https://www.sunrealtync.com/outer-banks/carova---4x4-beaches-nc-rentals/oceanside/swb-36"
            ))
        return _fake_response(text=_DETAIL_HTML)

    monkeypatch.setattr(_client.requests, "get", fake_get)
    _client.get_rental_details("SWB-36")
    # Solr call should contain lowercase property code
    solr_calls = [c for c in calls if "solr" in c]
    assert solr_calls


def test_get_rental_details_by_full_url(monkeypatch):
    calls = []

    def fake_get(url, *args, **kwargs):
        calls.append(url)
        return _fake_response(text=_DETAIL_HTML)

    monkeypatch.setattr(_client.requests, "get", fake_get)
    d = _client.get_rental_details(
        "https://www.sunrealtync.com/outer-banks/duck-nc-rentals/oceanfront/655"
    )
    # Full URL should be fetched directly without Solr
    assert not any("solr" in url for url in calls)
    assert d["bedrooms"] == 4


def test_get_rental_details_amenities(monkeypatch):
    monkeypatch.setattr(_client.requests, "get", _make_detail_fake_get())
    d = _client.get_rental_details("655")
    assert "Ocean view" in d["amenities"]
    assert "Private Pool" in d["amenities"]


def test_get_rental_details_images(monkeypatch):
    monkeypatch.setattr(_client.requests, "get", _make_detail_fake_get())
    d = _client.get_rental_details("655")
    assert len(d["image_urls"]) >= 2
    assert all("rezfusion" in url for url in d["image_urls"])


def test_get_rental_details_availability_windows(monkeypatch):
    monkeypatch.setattr(_client.requests, "get", _make_detail_fake_get())
    d = _client.get_rental_details("655")
    assert len(d["availability_windows"]) >= 1
    avail = [w for w in d["availability_windows"] if w["available"]]
    assert len(avail) >= 1


def test_get_rental_details_schema_drift_raises(monkeypatch):
    def fake_get(url, *args, **kwargs):
        if "solr" in url:
            return _fake_response(_solr_resolve_payload(
                "https://www.sunrealtync.com/outer-banks/duck-nc-rentals/oceanfront/655"
            ))
        return _fake_response(text="<html><body>no title div</body></html>")

    monkeypatch.setattr(_client.requests, "get", fake_get)
    with pytest.raises(RuntimeError, match="Unexpected Sun Realty response shape"):
        _client.get_rental_details("655")


# ---------- MCP server tools ----------


def test_mcp_search_rentals_tool(monkeypatch):
    docs = [_solr_doc("A", beds=5), _solr_doc("B", beds=3)]
    monkeypatch.setattr(
        _client.requests, "get", lambda *a, **kw: _fake_response(_solr_payload(docs))
    )
    result = asyncio.run(server.search_rentals(town="duck", min_bedrooms=4))
    ids = [li["listing_id"] for li in result["listings"]]
    assert "A" in ids
    assert "B" not in ids


def test_mcp_get_rental_details_tool(monkeypatch):
    monkeypatch.setattr(_client.requests, "get", _make_detail_fake_get())
    result = asyncio.run(server.get_rental_details("655"))
    assert result["bedrooms"] == 4
    assert result["bathrooms_full"] == 3
