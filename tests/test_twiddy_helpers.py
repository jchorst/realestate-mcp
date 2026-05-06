"""Unit tests for pure helper functions in the Twiddy client."""

from __future__ import annotations

import pytest

from realestate_mcp.servers.twiddy import _client


@pytest.mark.parametrize(
    "summary, expected_full, expected_half",
    [
        ("9 Full 1 Half", 9, 1),
        ("3 Full 0 Half", 3, 0),
        ("6 Full", 6, 0),
        ("1 Full 1 Half", 1, 1),
        ("12 Full 2 Half", 12, 2),
        (None, None, None),
        ("", None, None),
    ],
)
def test_parse_baths_summary(summary, expected_full, expected_half):
    full, half = _client._parse_baths_summary(summary)
    assert full == expected_full
    assert half == expected_half


@pytest.mark.parametrize(
    "bedrooms_str, expected",
    [
        ("10 beds", 10),
        ("1 beds", 1),
        ("3 beds", 3),
        ("24 beds", 24),
        (None, None),
        ("", None),
        ("no number here", None),
    ],
)
def test_parse_bedrooms(bedrooms_str, expected):
    assert _client._parse_bedrooms(bedrooms_str) == expected


@pytest.mark.parametrize(
    "token, expected",
    [
        (
            "392559?v=abc123",
            "https://www.twiddy.com/property-images/392559?v=abc123",
        ),
        ("123456?v=xyz", "https://www.twiddy.com/property-images/123456?v=xyz"),
        (None, None),
        ("", None),
    ],
)
def test_build_image_url(token, expected):
    assert _client._build_image_url(token) == expected


@pytest.mark.parametrize(
    "prop_url, expected_neighborhood",
    [
        ("/outer-banks/corolla/pine-island/rentals/station-one/", "Pine Island"),
        ("/outer-banks/duck/sand-hills/rentals/dune-thing/", "Sand Hills"),
        ("/outer-banks/corolla/pine-island-reserve/rentals/some-house/", "Pine Island Reserve"),
        ("/outer-banks/corolla/whalehead/rentals/some-house/", "Whalehead"),
        ("/bad/url/", None),
        ("", None),
    ],
)
def test_extract_neighborhood(prop_url, expected_neighborhood):
    assert _client._extract_neighborhood(prop_url) == expected_neighborhood


@pytest.mark.parametrize(
    "input_id, expected",
    [
        ("5744", 5744),
        ("12345", 12345),
        ("0001", 1),
    ],
)
def test_coerce_id_from_plain_string(input_id, expected):
    assert _client._coerce_id(input_id) == expected


def test_coerce_id_raises_on_non_url_non_numeric():
    with pytest.raises(ValueError, match="Cannot extract listing ID"):
        _client._coerce_id("not-a-url-or-number")


@pytest.mark.parametrize("input_id", [5744, 0, 12345])
def test_coerce_id_accepts_bare_int(input_id):
    assert _client._coerce_id(input_id) == input_id


@pytest.mark.parametrize(
    "html, expected",
    [
        ("<p>Hello world</p>", "Hello world"),
        ("plain text", "plain text"),
        ("<h3>Title</h3><p>Body</p>", "Title Body"),
        ("text\xa0nbsp", "text nbsp"),
        ("&nbsp;leading", "leading"),
        ("", ""),
        (None, ""),
    ],
)
def test_strip_html(html, expected):
    result = _client._strip_html(html)
    assert " ".join(result.split()) == " ".join(expected.split())


def test_town_names_contains_expected_towns():
    expected = {"corolla", "duck", "southern-shores", "kill-devil-hills", "nags-head", "4x4"}
    assert set(_client.TOWN_NAMES.keys()) == expected


def test_town_names_values_are_non_empty_strings():
    for slug, name in _client.TOWN_NAMES.items():
        assert isinstance(name, str), f"{slug} name must be a string"
        assert name, f"{slug} name must not be empty"
