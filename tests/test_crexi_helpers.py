"""Unit tests for pure helper functions in the Crexi client."""

from __future__ import annotations

import pytest

from realestate_mcp.servers.crexi import _client


@pytest.mark.parametrize(
    "input_, expected",
    [
        (12558, "12558"),
        ("12558", "12558"),
        ("https://www.crexi.com/properties/california-maple-ave/12558", "12558"),
        ("https://www.crexi.com/properties/some-slug/99999", "99999"),
        ("california-maple-ave/12558", "12558"),
    ],
)
def test_coerce_id_valid(input_, expected):
    assert _client._coerce_id(input_) == expected


def test_coerce_id_int_zero():
    assert _client._coerce_id(0) == "0"


def test_coerce_id_invalid_raises():
    with pytest.raises(ValueError, match="Cannot extract listing ID"):
        _client._coerce_id("not-a-valid-id-or-url")


def test_coerce_id_empty_string_raises():
    with pytest.raises(ValueError, match="Cannot extract listing ID"):
        _client._coerce_id("")


def test_coerce_id_rejects_hex_property_record_ids():
    """Hex IDs from /properties/search aren't actionable against /assets/{id};
    rejecting them surfaces the mismatch as a ValueError instead of a 404."""
    with pytest.raises(ValueError, match="Cannot extract listing ID"):
        _client._coerce_id("7812140424d5c1dd1ec26c4091031a29d443230f")


@pytest.mark.parametrize(
    "details, expected",
    [
        ({"Lot Size (acres)": "1.05"}, 1.05),
        ({"Lot Size (Acres)": "2.3"}, 2.3),
        ({"Land Area (acres)": "0.5"}, 0.5),
        ({"Lot Size (acres)": "1,234.5"}, 1234.5),
        ({}, None),
        ({"Lot Size (acres)": "N/A"}, None),
        ({"Other Key": "1.0"}, None),
    ],
)
def test_extract_lot_acres(details, expected):
    assert _client._extract_lot_acres(details) == expected


@pytest.mark.parametrize(
    "summary_details, expected",
    [
        ([{"key": "SquareFootage", "value": 12200}], 12200),
        ([{"key": "Other", "value": 999}, {"key": "SquareFootage", "value": 5000}], 5000),
        ([{"key": "SquareFootage", "value": "bad"}], None),
        ([{"key": "SquareFootage", "value": None}], None),
        ([], None),
    ],
)
def test_extract_sqft_from_summary(summary_details, expected):
    assert _client._extract_sqft_from_summary(summary_details) == expected


@pytest.mark.parametrize(
    "details, expected",
    [
        ({"Year Built": "1955"}, "1955"),
        ({"Year Renovated": "1990"}, "1990"),
        ({"Year Built": "1924", "Year Renovated": "1972"}, "1924"),
        ({}, None),
    ],
)
def test_extract_year_built(details, expected):
    assert _client._extract_year_built(details) == expected


@pytest.mark.parametrize(
    "locations, expected",
    [
        (
            [{"address": "123 Main St", "city": "Atlanta", "state": {"code": "GA"}, "zip": "30301"}],  # noqa: E501
            ("123 Main St", "Atlanta", "GA", "30301"),
        ),
        (
            [{"address": "", "city": "Nashville", "state": {"code": "TN"}, "zip": "37201"}],
            ("", "Nashville", "TN", "37201"),
        ),
        ([], ("", "", "", "")),
        (
            [{"address": "456 Oak Ave", "city": "Dallas", "state": None, "zip": "75201"}],
            ("456 Oak Ave", "Dallas", "", "75201"),
        ),
    ],
)
def test_parse_location(locations, expected):
    assert _client._parse_location(locations) == expected
