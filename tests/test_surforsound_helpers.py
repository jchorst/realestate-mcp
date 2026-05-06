"""Unit tests for pure helper functions in the Surf or Sound client."""

from __future__ import annotations

import pytest

from realestate_mcp.servers.surforsound import _client


@pytest.mark.parametrize(
    "bath_text, expected_full, expected_half",
    [
        ("8 Full, 2 Half", 8, 2),
        ("3 Full", 3, 0),
        ("12 Full, 1 Half", 12, 1),
        ("1 Full, 1 Half", 1, 1),
        ("6 Full, 0 Half", 6, 0),
        (None, None, None),
        ("", None, None),
        ("no numbers", None, 0),
    ],
)
def test_parse_baths(bath_text, expected_full, expected_half):
    full, half = _client._parse_baths(bath_text)
    assert full == expected_full
    assert half == expected_half


@pytest.mark.parametrize(
    "price_text, expected",
    [
        ("$4,995 / week", 4995.0),
        ("$4,995 /week", 4995.0),
        ("$1,200", 1200.0),
        ("$14,495", 14495.0),
        ("no price", None),
        (None, None),
        ("", None),
    ],
)
def test_parse_price(price_text, expected):
    assert _client._parse_price(price_text) == expected


@pytest.mark.parametrize(
    "input_id, expected",
    [
        ("553", 553),
        ("1204", 1204),
        ("0001", 1),
    ],
)
def test_coerce_id_from_plain_string(input_id, expected):
    assert _client._coerce_id(input_id) == expected


@pytest.mark.parametrize("bare_int", [553, 0, 1204])
def test_coerce_id_accepts_bare_int(bare_int):
    assert _client._coerce_id(bare_int) == bare_int


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://www.surforsound.com/hatteras-vacation-rental/property/553", 553),
        ("/hatteras-vacation-rental/property/1204", 1204),
        ("https://www.surforsound.com/hatteras-vacation-rental/property/77?Checkin=2026-07-04", 77),
    ],
)
def test_coerce_id_from_url(url, expected):
    assert _client._coerce_id(url) == expected


def test_coerce_id_raises_on_garbage():
    with pytest.raises(ValueError, match="Cannot extract listing ID"):
        _client._coerce_id("not-a-url-or-number")


@pytest.mark.parametrize(
    "html, expected",
    [
        ("<p>Hello world</p>", "Hello world"),
        ("plain text", "plain text"),
        ("<h3>Title</h3><p>Body</p>", "Title  Body"),
        ("text\xa0nbsp", "text nbsp"),
        ("&nbsp;leading", "leading"),
        ("", ""),
        (None, ""),
    ],
)
def test_strip_html(html, expected):
    result = _client._strip_html(html)
    assert " ".join(result.split()) == " ".join(expected.split())


def test_village_slugs_contains_expected():
    expected = {"rodanthe", "waves", "salvo", "avon", "buxton", "frisco", "hatteras"}
    assert expected == _client.VILLAGE_SLUGS


def test_village_slugs_does_not_contain_ocracoke():
    assert "ocracoke" not in _client.VILLAGE_SLUGS
