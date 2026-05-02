"""Unit tests for pure helper functions in the Airbnb client."""

from __future__ import annotations

import pytest

from realestate_mcp.servers.airbnb import _client


@pytest.mark.parametrize(
    "text, expected",
    [
        ("3 bedrooms", 3),
        ("1 bedroom", 1),
        ("Studio", 0),
        ("studio apartment", 0),
        ("12 beds", 12),
        ("", None),
        (None, None),
        ("no number here", None),
    ],
)
def test_coerce_int(text, expected):
    assert _client._coerce_int(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("2.5 baths", 2.5),
        ("1 bath", 1.0),
        ("1.0 bath", 1.0),
        ("0.5 bath", 0.5),
        ("Half bath", 0.5),
        ("", None),
        (None, None),
    ],
)
def test_coerce_float(text, expected):
    assert _client._coerce_float(text) == expected


@pytest.mark.parametrize(
    "encoded, expected",
    [
        # base64("DemandStayListing:23739741")
        ("RGVtYW5kU3RheUxpc3Rpbmc6MjM3Mzk3NDE=", "23739741"),
        # base64("DemandStayListing:821030675435216627")
        ("RGVtYW5kU3RheUxpc3Rpbmc6ODIxMDMwNjc1NDM1MjE2NjI3", "821030675435216627"),
        ("", None),
        (None, None),
        ("not_base64!!!", None),
    ],
)
def test_decode_listing_id(encoded, expected):
    assert _client._decode_listing_id(encoded) == expected


@pytest.mark.parametrize(
    "price_text, expected",
    [
        ("$1,450", (1450.0, "$")),
        ("$1,507", (1507.0, "$")),
        ("$753", (753.0, "$")),
        ("€1,200", (1200.0, "€")),
        ("£999.50", (999.5, "£")),
        ("", (None, None)),
        (None, (None, None)),
        ("free", (None, None)),
    ],
)
def test_parse_price(price_text, expected):
    assert _client._parse_price(price_text) == expected


@pytest.mark.parametrize(
    "html, expected",
    [
        ("<p>hello world</p>", "hello world"),
        ("plain text", "plain text"),
        ("<div><br/>line<br/>break</div>", "line  break"),
        ("nbsp\xa0space", "nbsp space"),
        ("&nbsp;leading", "leading"),
        ("", ""),
        (None, ""),
    ],
)
def test_strip_html(html, expected):
    # Multiple whitespace collapses can vary; check substring or normalized form
    result = _client._strip_html(html)
    assert " ".join(result.split()) == " ".join(expected.split())


@pytest.mark.parametrize(
    "input_, expected",
    [
        ("23739741", "23739741"),
        ("https://www.airbnb.com/rooms/23739741", "23739741"),
        ("https://www.airbnb.com/rooms/23739741?checkin=2026-01-01", "23739741"),
        ("/rooms/821030675435216627", "821030675435216627"),
    ],
)
def test_coerce_listing_id(input_, expected):
    assert _client._coerce_listing_id(input_) == expected


def test_coerce_listing_id_invalid():
    with pytest.raises(ValueError, match="Cannot extract"):
        _client._coerce_listing_id("not a url or id")


def test_structured_field_finds_first_match():
    sc = {
        "primaryLine": [
            {"body": "3 bedrooms"},
            {"body": "5 beds"},
            {"body": "2.5 baths"},
        ]
    }
    assert _client._structured_field(sc, "bedroom") == "3 bedrooms"
    assert _client._structured_field(sc, "bath") == "2.5 baths"


def test_structured_field_missing_returns_none():
    sc = {"primaryLine": [{"body": "3 bedrooms"}]}
    assert _client._structured_field(sc, "bath") is None


def test_structured_field_empty():
    assert _client._structured_field({}, "bath") is None
    assert _client._structured_field({"primaryLine": None}, "bath") is None
