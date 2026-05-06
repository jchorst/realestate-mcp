# ruff: noqa: E501
"""Tests for Sun Realty parsers with hand-crafted minimal fixtures.

Fixtures are shaped after the real Solr and HTML responses observed on
2026-05-05. The HTML fixtures use the actual CSS classes from the live site
to ensure selectors are correct. Long lines in HTML fixture strings are
intentional and exempt from the line-length rule.
"""

from __future__ import annotations

import json

import pytest

from realestate_mcp.servers.sunrealty import _client

# ---------- Solr fixture builders ----------


def _solr_doc(
    *,
    item_id: str = "655",
    ss_name: str = "The Blue Whale SWB-36",
    ss_url: str = "https://www.sunrealtync.com/outer-banks/carova---4x4-beaches-nc-rentals/oceanside/swb-36",
    beds: int = 5,
    baths: float = 3.0,
    sleeps: int = 8,
    town: str = "Carova / 4x4 Beaches",
    community: str = "Carova / 4x4 Beaches",
    distance: str = "Oceanside",
    amenities: list[str] | None = None,
    image: str = "https://images.rezfusion.com?source=example.jpg",
) -> dict:
    if amenities is None:
        amenities = ["Pet Friendly", "Private Pool", "WiFi"]
    return {
        "item_id": item_id,
        "is_eid": int(item_id),
        "ss_name": ss_name,
        "ss_url": ss_url,
        "is_nid$field_beds": beds,
        "fs_rc_core_lodging_product$baths": baths,
        "is_rc_core_lodging_product$occ_total": sleeps,
        "sm_nid$rc_core_term_town$name": [town],
        "sm_nid$rc_core_term_community$name": [community],
        "sm_nid$rc_core_term_distance_to_beach$name": [distance],
        "sm_nid$rc_core_term_featured_amenities$name": amenities,
        "sm_rc_core_item_teaser_slideshow": [image],
        "ss_vrweb_default_image": image,
    }


def _solr_payload(docs: list[dict], num_found: int | None = None) -> dict:
    return {
        "response": {
            "numFound": num_found if num_found is not None else len(docs),
            "start": 0,
            "docs": docs,
        }
    }


# ---------- _parse_search_results ----------


def test_parse_search_results_basic():
    payload = _solr_payload([_solr_doc()])
    listings = _client._parse_search_results(payload)
    assert len(listings) == 1
    li = listings[0]
    assert li.listing_id == "655"
    assert li.name == "The Blue Whale SWB-36"
    assert li.bedrooms == 5
    assert li.bathrooms_full == 3
    assert li.bathrooms_half == 0
    assert li.sleeps == 8
    assert li.town == "Carova / 4x4 Beaches"
    assert li.community == "Carova / 4x4 Beaches"
    assert li.distance_to_beach == "Oceanside"
    assert "Pet Friendly" in li.featured_amenities
    assert "rezfusion" in (li.image_url or "")


def test_parse_search_results_half_bath():
    payload = _solr_payload([_solr_doc(baths=5.5)])
    listings = _client._parse_search_results(payload)
    assert listings[0].bathrooms_full == 5
    assert listings[0].bathrooms_half == 1


def test_parse_search_results_multiple_listings():
    docs = [_solr_doc(item_id=str(i), ss_name=f"House {i}", beds=i + 2) for i in range(5)]
    payload = _solr_payload(docs)
    listings = _client._parse_search_results(payload)
    assert len(listings) == 5
    assert listings[2].bedrooms == 4


def test_parse_search_results_empty():
    payload = _solr_payload([])
    listings = _client._parse_search_results(payload)
    assert listings == []


def test_parse_search_results_check_in_propagated():
    payload = _solr_payload([_solr_doc()])
    listings = _client._parse_search_results(payload, check_in="2026-06-21")
    assert listings[0].check_in == "2026-06-21"


def test_parse_search_results_raises_on_missing_response_key():
    with pytest.raises(RuntimeError, match="Unexpected Sun Realty response shape"):
        _client._parse_search_results({"wrong": "key"})


def test_parse_search_results_raises_on_missing_docs_key():
    with pytest.raises(RuntimeError, match="Unexpected Sun Realty response shape"):
        _client._parse_search_results({"response": {"numFound": 0}})


def test_parse_search_results_skips_doc_without_item_id():
    bad_doc = {k: v for k, v in _solr_doc().items() if k not in ("item_id", "is_eid")}
    good_doc = _solr_doc(item_id="100", ss_name="Good House")
    payload = _solr_payload([bad_doc, good_doc])
    listings = _client._parse_search_results(payload)
    assert len(listings) == 1
    assert listings[0].listing_id == "100"


def test_parse_search_results_missing_optional_fields_dont_crash():
    minimal = {"item_id": "1", "ss_name": "Minimal"}
    payload = _solr_payload([minimal])
    listings = _client._parse_search_results(payload)
    assert len(listings) == 1
    assert listings[0].bedrooms is None
    assert listings[0].bathrooms_full is None
    assert listings[0].bathrooms_half is None
    assert listings[0].sleeps is None
    assert listings[0].town == ""
    assert listings[0].image_url is None


# ---------- _parse_avail_form ----------

_AVAIL_FORM_SCRIPT = json.dumps(
    {
        "rcItemAvailForm": [
            {
                "eid": "655",
                "tdc": "7",
                "avail": [
                    {"b": "2026-04-28", "e": "2026-05-02", "a": "0", "q": "0", "s": "0", "x": ""},
                    {"b": "2026-05-03", "e": "2026-06-13", "a": "1", "q": "1", "s": "1", "x": ""},
                    {"b": "2026-06-14", "e": "2026-06-20", "a": "0", "q": "0", "s": "0", "x": ""},
                ],
            }
        ]
    }
)

_AVAIL_HTML = f"""<html><body>
<script>
jQuery.extend(Drupal.settings, {_AVAIL_FORM_SCRIPT});
</script>
</body></html>"""


def test_parse_avail_form_basic():
    windows = _client._parse_avail_form(_AVAIL_HTML)
    assert len(windows) == 3
    assert windows[0].start == "2026-04-28"
    assert windows[0].end == "2026-05-02"
    assert windows[0].available is False
    assert windows[1].available is True
    assert windows[2].available is False


def test_parse_avail_form_empty_on_no_match():
    windows = _client._parse_avail_form("<html><body>no avail data</body></html>")
    assert windows == []


def test_parse_avail_form_empty_on_malformed_json():
    bad_html = '<script>"rcItemAvailForm": [{bad json}</script>'
    windows = _client._parse_avail_form(bad_html)
    assert windows == []


# ---------- _parse_detail_page ----------

# Minimal HTML fixture based on real Sun Realty detail page structure (2026-05-05).
_DETAIL_HTML = """<!DOCTYPE html>
<html>
<head><title>Sun Realty</title></head>
<body>
<h1><a href="/">Sun Realty</a></h1>
<h1>The Blue Whale SWB-36</h1>
<div class="field field-name-title">The Blue Whale SWB-36</div>
<div class="rc-lodging-beds rc-lodging-detail">Bedrooms: 4</div>
<div class="rc-lodging-baths rc-lodging-detail">Bathrooms: 3 &amp; 1 Half</div>
<div class="field field-name-field-town">Carova</div>
<div class="field field-name-rc-core-term-community">Carova / 4x4 Beaches</div>
<div class="field field-name-body">
  If you are searching for an unforgettable 4x4 home with a list of amenities that will make
  you never want to leave the OBX, The Blue Whale is the one for you and your family!
  Enjoy the ocean view from multiple decks, a private pool, hot tub, and game room.
</div>
<div class="group-vr-full-amenities group-vr-property-amenities field-group-foundation_group_section_item">
  <h3>Amenities &amp; Beds</h3>
  <div class="item-list">
    <ul>
      <li>Ocean view</li>
      <li>Pet Friendly</li>
      <li>Private Pool</li>
    </ul>
  </div>
  <div class="item-list">
    <ul>
      <li>Hot Tub</li>
      <li>WiFi</li>
    </ul>
  </div>
</div>
<img src="https://images.rezfusion.com?width=1280&amp;source=img1.jpg" />
<img src="https://images.rezfusion.com?width=1280&amp;source=img2.jpg" />
<img data-src="https://images.rezfusion.com?width=1280&amp;source=img3.jpg" />
<script>
jQuery.extend(Drupal.settings, {"rcItemAvailForm": [{"eid": "655", "avail":
  [{"b": "2026-05-03", "e": "2026-06-13", "a": "1", "q": "1", "s": "1", "x": ""},
   {"b": "2026-06-14", "e": "2026-06-20", "a": "0", "q": "0", "s": "0", "x": ""}]}]});
</script>
</body>
</html>"""


def test_parse_detail_page_name():
    d = _client._parse_detail_page(_DETAIL_HTML, "https://example.com/prop")
    assert d.name == "The Blue Whale SWB-36"


def test_parse_detail_page_bedrooms():
    d = _client._parse_detail_page(_DETAIL_HTML, "https://example.com/prop")
    assert d.bedrooms == 4


def test_parse_detail_page_bathrooms():
    d = _client._parse_detail_page(_DETAIL_HTML, "https://example.com/prop")
    assert d.bathrooms_full == 3
    assert d.bathrooms_half == 1


def test_parse_detail_page_town():
    d = _client._parse_detail_page(_DETAIL_HTML, "https://example.com/prop")
    assert d.town == "Carova"


def test_parse_detail_page_community():
    d = _client._parse_detail_page(_DETAIL_HTML, "https://example.com/prop")
    assert d.community == "Carova / 4x4 Beaches"


def test_parse_detail_page_description():
    d = _client._parse_detail_page(_DETAIL_HTML, "https://example.com/prop")
    assert "Blue Whale" in d.description
    assert len(d.description) > 50


def test_parse_detail_page_amenities():
    d = _client._parse_detail_page(_DETAIL_HTML, "https://example.com/prop")
    assert "Ocean view" in d.amenities
    assert "Pet Friendly" in d.amenities
    assert "Private Pool" in d.amenities
    assert "Hot Tub" in d.amenities
    assert "WiFi" in d.amenities


def test_parse_detail_page_images():
    d = _client._parse_detail_page(_DETAIL_HTML, "https://example.com/prop")
    assert len(d.image_urls) >= 3
    assert all("rezfusion" in url for url in d.image_urls)


def test_parse_detail_page_availability_windows():
    d = _client._parse_detail_page(_DETAIL_HTML, "https://example.com/prop")
    assert len(d.availability_windows) == 2
    avail = [w for w in d.availability_windows if w["available"]]
    assert len(avail) == 1
    assert avail[0]["start"] == "2026-05-03"


def test_parse_detail_page_sleeps_is_none():
    d = _client._parse_detail_page(_DETAIL_HTML, "https://example.com/prop")
    assert d.sleeps is None


def test_parse_detail_page_raises_on_missing_title():
    bad_html = "<html><body><p>No title div here</p></body></html>"
    with pytest.raises(RuntimeError, match="Unexpected Sun Realty response shape"):
        _client._parse_detail_page(bad_html, "https://example.com/bad")


def test_parse_detail_page_to_dict():
    d = _client._parse_detail_page(_DETAIL_HTML, "https://example.com/prop")
    result = d.to_dict()
    assert isinstance(result, dict)
    assert "listing_id" in result
    assert "amenities" in result
    assert "image_urls" in result
    assert "availability_windows" in result
