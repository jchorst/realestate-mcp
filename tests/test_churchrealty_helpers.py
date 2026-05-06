"""Unit tests for pure helper functions in the Church Realty client."""

from __future__ import annotations

import pytest

from realestate_mcp.servers.churchrealty import _client

# ---------- _coerce_id ----------


@pytest.mark.parametrize(
    "input_, expected",
    [
        # Bare slug string
        (
            "church-property-for-sale-houston-tx-10355-mills-road",
            "church-property-for-sale-houston-tx-10355-mills-road",
        ),
        # Full URL with trailing slash
        (
            "https://www.churchrealty.com/property/church-property-for-sale-houston-tx-10355-mills-road/",
            "church-property-for-sale-houston-tx-10355-mills-road",
        ),
        # Full URL without trailing slash
        (
            "https://www.churchrealty.com/property/church-property-for-sale-fort-worth-tx-3321-cleburne-road",
            "church-property-for-sale-fort-worth-tx-3321-cleburne-road",
        ),
        # Int accepted (converted to string)
        (12345, "12345"),
        # Int as string
        ("553", "553"),
    ],
)
def test_coerce_id(input_, expected):
    assert _client._coerce_id(input_) == expected


def test_coerce_id_accepts_int():
    result = _client._coerce_id(42)
    assert isinstance(result, str)
    assert result == "42"


# ---------- _listing_type_from_slug ----------


@pytest.mark.parametrize(
    "slug, expected",
    [
        ("church-property-for-sale-houston-tx", "For Sale"),
        ("multi-use-space-for-lease-arlington-tx-7000-matlock-road", "For Lease"),
        ("shared-church-space-for-lease-pilot-point-11010-hwy-377", "For Lease"),
        ("preston-road-10-acre-developed-site-for-sale-5625-preston-road", "For Sale"),
        ("some-property-no-type-indicated", "Unknown"),
        ("", "Unknown"),
    ],
)
def test_listing_type_from_slug(slug, expected):
    assert _client._listing_type_from_slug(slug) == expected


# ---------- _parse_price ----------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Price: $3,900,000", 3900000.0),
        ("Price: $750,000", 750000.0),
        ("$1,200,000", 1200000.0),
        ("Please call agent for price", None),
        ("Please call broker for price", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_price(text, expected):
    assert _client._parse_price(text) == expected


# ---------- _parse_int ----------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("51,325 sqft", 51325),
        ("13,743 sqft", 13743),
        ("24,542 sqft plus 3,000 sqft of portable bldgs", 24542),
        ("450", 450),
        ("~9.94 acres", 9),
        ("", None),
        (None, None),
    ],
)
def test_parse_int(text, expected):
    assert _client._parse_int(text) == expected


# ---------- _parse_float ----------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("4.52 acres", 4.52),
        ("9.94 acres", 9.94),
        ("10 acres", 10.0),
        ("", None),
        (None, None),
    ],
)
def test_parse_float(text, expected):
    assert _client._parse_float(text) == expected


# ---------- _parse_address_line2 ----------


@pytest.mark.parametrize(
    "line2, expected",
    [
        ("La Porte, TX 77571", ("La Porte", "TX", "77571")),
        ("Houston, TX 77015", ("Houston", "TX", "77015")),
        ("Fort Worth, TX 76110", ("Fort Worth", "TX", "76110")),
        ("Pilot Point, TX 76258", ("Pilot Point", "TX", "76258")),
        ("Rowlett, TX 75088", ("Rowlett", "TX", "75088")),
        ("Dallas, TX 75228", ("Dallas", "TX", "75228")),
        # Malformed — returns empty strings, no crash
        ("Not a valid address", ("", "", "")),
        ("", ("", "", "")),
    ],
)
def test_parse_address_line2(line2, expected):
    assert _client._parse_address_line2(line2) == expected


# ---------- _slug_from_url ----------


@pytest.mark.parametrize(
    "url, expected",
    [
        (
            "https://www.churchrealty.com/property/church-property-for-sale-houston-tx-10355-mills-road/",
            "church-property-for-sale-houston-tx-10355-mills-road",
        ),
        (
            "https://www.churchrealty.com/property/church-property-for-sale-houston-tx-10355-mills-road",
            "church-property-for-sale-houston-tx-10355-mills-road",
        ),
    ],
)
def test_slug_from_url(url, expected):
    assert _client._slug_from_url(url) == expected
