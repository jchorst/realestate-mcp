"""Unit tests for pure helper functions in the Carolina Designs client."""

from __future__ import annotations

import pytest

from realestate_mcp.servers.carolinadesigns import _client


@pytest.mark.parametrize(
    "baths_str, expected_full, expected_half",
    [
        ("15/2", 15, 2),
        ("3/1", 3, 1),
        ("6/0", 6, 0),
        ("3", 3, 0),
        ("12/3", 12, 3),
        (None, None, None),
        ("", None, None),
    ],
)
def test_parse_baths(baths_str, expected_full, expected_half):
    full, half = _client._parse_baths(baths_str)
    assert full == expected_full
    assert half == expected_half


@pytest.mark.parametrize(
    "input_, expected_id",
    [
        ("161", "161"),
        ("054", "054"),
        ("https://www.carolinadesigns.com/corolla-vacation-rental/161-ocean-sol/", "161"),
        ("https://www.carolinadesigns.com/property-detail-page/161", "161"),
        ("/property-detail-page/054", "054"),
        ("  1234  ", "1234"),
    ],
)
def test_coerce_id(input_, expected_id):
    assert _client._coerce_id(input_) == expected_id


def test_coerce_id_raises_on_no_id():
    with pytest.raises(ValueError, match="Cannot extract listing ID"):
        _client._coerce_id("no-numbers-in-slug")


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


def test_town_ids_contains_all_six_towns():
    expected = {"corolla", "duck", "southern-shores", "kitty-hawk", "kill-devil-hills", "nags-head"}
    assert set(_client.TOWN_IDS.keys()) == expected


def test_town_ids_values_are_strings():
    for slug, tid in _client.TOWN_IDS.items():
        assert isinstance(tid, str), f"{slug} id must be a string"
        assert tid.isdigit(), f"{slug} id {tid!r} must be numeric"
