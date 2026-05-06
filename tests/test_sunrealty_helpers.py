"""Unit tests for pure helper functions in the Sun Realty client."""

from __future__ import annotations

import pytest

from realestate_mcp.servers.sunrealty import _client

# ---------- _parse_baths_float ----------


@pytest.mark.parametrize(
    "baths_float, expected_full, expected_half",
    [
        (2.0, 2, 0),
        (3.0, 3, 0),
        (5.0, 5, 0),
        (3.5, 3, 1),
        (5.5, 5, 1),
        (1.5, 1, 1),
        (0.0, 0, 0),
        (None, None, None),
    ],
)
def test_parse_baths_float(baths_float, expected_full, expected_half):
    full, half = _client._parse_baths_float(baths_float)
    assert full == expected_full
    assert half == expected_half


# ---------- _parse_baths_text ----------


@pytest.mark.parametrize(
    "baths_text, expected_full, expected_half",
    [
        ("Bathrooms: 2", 2, 0),
        ("Bathrooms: 3 & 1 Half", 3, 1),
        ("Bathrooms: 5 & 1 Half", 5, 1),
        ("Bathrooms: 10", 10, 0),
        ("2", 2, 0),
        (None, None, None),
        ("", None, None),
    ],
)
def test_parse_baths_text(baths_text, expected_full, expected_half):
    full, half = _client._parse_baths_text(baths_text)
    assert full == expected_full
    assert half == expected_half


# ---------- _coerce_id ----------


@pytest.mark.parametrize(
    "input_, expected",
    [
        # Bare integers
        (655, "655"),
        (3, "3"),
        # Numeric strings
        ("655", "655"),
        ("3", "3"),
        ("  655  ", "655"),
        # Full URL → returned as-is
        (
            "https://www.sunrealtync.com/outer-banks/carova---4x4-beaches-nc-rentals/oceanside/swb-36",
            "https://www.sunrealtync.com/outer-banks/carova---4x4-beaches-nc-rentals/oceanside/swb-36",
        ),
        # Bare path
        (
            "/outer-banks/duck-nc-rentals/oceanfront/110",
            "/outer-banks/duck-nc-rentals/oceanfront/110",
        ),
        # Alphanumeric property codes — normalised to lowercase
        ("SWB-36", "swb-36"),
        ("swb-36", "swb-36"),
        ("14-E", "14-e"),
        ("110-D", "110-d"),
        ("INS-C4", "ins-c4"),
    ],
)
def test_coerce_id(input_, expected):
    assert _client._coerce_id(input_) == expected


def test_coerce_id_accepts_bare_int():
    result = _client._coerce_id(655)
    assert result == "655"
    assert isinstance(result, str)


def test_coerce_id_accepts_alphanumeric():
    result = _client._coerce_id("SWB-36")
    assert result == "swb-36"


def test_coerce_id_accepts_numeric_string():
    result = _client._coerce_id("655")
    assert result == "655"


# ---------- _strip_html ----------


@pytest.mark.parametrize(
    "html, expected",
    [
        ("<p>Hello world</p>", "Hello world"),
        ("plain text", "plain text"),
        ("<h3>Title</h3><p>Body</p>", "Title Body"),
        ("text\xa0nbsp", "text nbsp"),
        ("", ""),
        (None, ""),
    ],
)
def test_strip_html(html, expected):
    result = _client._strip_html(html)
    assert " ".join(result.split()) == " ".join(expected.split())


# ---------- TOWN_NAMES ----------


def test_town_names_contains_all_expected_slugs():
    required = {
        "duck",
        "corolla",
        "kill-devil-hills",
        "south-nags-head",
        "nags-head",
        "avon",
        "kitty-hawk",
        "salvo",
        "carova",
        "4x4",
        "rodanthe",
        "southern-shores",
        "hatteras",
        "waves",
        "manteo",
    }
    assert required.issubset(set(_client.TOWN_NAMES.keys()))


def test_town_names_values_are_non_empty_strings():
    for slug, display in _client.TOWN_NAMES.items():
        assert isinstance(display, str), f"{slug} display must be a string"
        assert display.strip(), f"{slug} display name must not be empty"


def test_carova_and_4x4_map_to_same_display():
    assert _client.TOWN_NAMES["carova"] == _client.TOWN_NAMES["4x4"]
