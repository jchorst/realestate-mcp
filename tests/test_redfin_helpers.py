"""Unit tests for pure helper functions in the Redfin client."""

from __future__ import annotations

import pytest

from realestate_mcp.servers.redfin import _client

# ---------------------------------------------------------------------------
# _coerce_id
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "input_, expected",
    [
        # Bare numeric string
        ("111190110", "111190110"),
        # Bare int
        (111190110, "111190110"),
        # Full URL
        (
            "https://www.redfin.com/NC/Arden/732-Streamside-Dr-28704/home/111190110",
            "111190110",
        ),
        # Relative URL path
        ("/NC/Arden/732-Streamside-Dr-28704/home/111190110", "111190110"),
        # URL with query params
        (
            "https://www.redfin.com/NC/Asheville/10-Main-St-28801/home/99887766?utm_source=google",
            "99887766",
        ),
        # Zero-padded (edge case — still treated as numeric)
        ("0", "0"),
    ],
)
def test_coerce_id(input_, expected):
    assert _client._coerce_id(input_) == expected


def test_coerce_id_int_and_str_equivalence():
    """Regression: int and str numeric ID must both work."""
    assert _client._coerce_id(111190110) == _client._coerce_id("111190110")


def test_coerce_id_invalid():
    with pytest.raises(ValueError, match="Cannot extract Redfin listing ID"):
        _client._coerce_id("not-a-url-or-id")


def test_coerce_id_invalid_slug_only():
    with pytest.raises(ValueError, match="Cannot extract Redfin listing ID"):
        _client._coerce_id("some-address-slug-without-home-segment")


# ---------------------------------------------------------------------------
# _image_url_from_home
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "home, expected",
    [
        # Normal webp case (confirmed live pattern)
        (
            {"mlsId": {"value": "4366321"}, "dataSourceId": 103, "photoFormat": "webp"},
            "https://ssl.cdn-redfin.com/photo/103/bigphoto/321/4366321_0.webp",
        ),
        # jpg fallback
        (
            {"mlsId": {"value": "4367198"}, "dataSourceId": 103, "photoFormat": "jpg"},
            "https://ssl.cdn-redfin.com/photo/103/bigphoto/198/4367198_0.jpg",
        ),
        # Missing photoFormat → None (per AGENTS.md, never hardcode the extension)
        ({"mlsId": {"value": "1234567"}, "dataSourceId": 77}, None),
        # Missing mlsId → None
        ({"dataSourceId": 103, "photoFormat": "webp"}, None),
        # Missing dataSourceId → None
        ({"mlsId": {"value": "4366321"}, "photoFormat": "webp"}, None),
        # Empty dict → None
        ({}, None),
    ],
)
def test_image_url_from_home(home, expected):
    assert _client._image_url_from_home(home) == expected


# ---------------------------------------------------------------------------
# _extract_description_from_html
# ---------------------------------------------------------------------------


def test_extract_description_basic():
    html = """
    <script type="application/ld+json">
    {"@context":"https://schema.org","@type":["Product","RealEstateListing"],
     "name":"732 Streamside Dr","description":"A lovely home in the mountains.",
     "url":"https://www.redfin.com/home/1"}
    </script>
    """
    assert _client._extract_description_from_html(html) == "A lovely home in the mountains."


def test_extract_description_unescapes_html_entities():
    html = """
    <script type="application/ld+json">
    {"@context":"https://schema.org","@type":["Product","RealEstateListing"],
     "name":"Test","description":"Owner&apos;s pride &amp; joy&mdash;stunning."}
    </script>
    """
    result = _client._extract_description_from_html(html)
    assert "'" in result  # &apos; -> '
    assert "&" in result  # &amp; -> &
    assert "—" in result  # &mdash; -> em dash (standard HTML5 entity)


def test_extract_description_returns_none_when_absent():
    html = "<html><body>no script tags</body></html>"
    assert _client._extract_description_from_html(html) is None


def test_extract_description_ignores_non_listing_blocks():
    html = """
    <script type="application/ld+json">
    {"@context":"http://schema.org","@type":"Organization","name":"Redfin"}
    </script>
    <script type="application/ld+json">
    {"@context":"https://schema.org","@type":["Product","RealEstateListing"],
     "name":"My Home","description":"This is the one."}
    </script>
    """
    assert _client._extract_description_from_html(html) == "This is the one."


# ---------------------------------------------------------------------------
# _extract_rss_json (structural)
# ---------------------------------------------------------------------------


def test_extract_rss_json_basic():
    body = '{"ReactServerAgent.cache": {"dataCache": {}}}'
    html = f"root.__reactServerState.InitialContext = {body};\n"
    result = _client._extract_rss_json(html)
    assert result == {"ReactServerAgent.cache": {"dataCache": {}}}


def test_extract_rss_json_handles_nested_braces():
    payload = '{"ReactServerAgent.cache": {"dataCache": {"key": {"value": {"nested": true}}}}}'
    html = (
        f"root.__reactServerState.InitialContext = {payload};\n"
        "root.__reactServerState.Config = {};"
    )
    result = _client._extract_rss_json(html)
    assert result["ReactServerAgent.cache"]["dataCache"]["key"]["value"]["nested"] is True


def test_extract_rss_json_raises_when_marker_missing():
    with pytest.raises(RuntimeError, match="Unexpected Redfin response shape"):
        _client._extract_rss_json("<html>no state here</html>")


def test_extract_rss_json_brace_inside_string_value():
    """The brace-depth walker must not count `{` or `}` inside JSON string literals."""
    payload = (
        '{"ReactServerAgent.cache":'
        ' {"dataCache": {"k": {"text": "value with {curly} braces and a } here"}}}}'
    )
    html = f"root.__reactServerState.InitialContext = {payload};\nroot.__reactServerState.x = 1;"
    result = _client._extract_rss_json(html)
    assert (
        result["ReactServerAgent.cache"]["dataCache"]["k"]["text"]
        == "value with {curly} braces and a } here"
    )


def test_extract_rss_json_raises_on_truncated_payload():
    """An unbalanced/truncated payload must raise RuntimeError, not JSONDecodeError."""
    truncated = 'root.__reactServerState.InitialContext = {"ReactServerAgent.cache":'
    with pytest.raises(RuntimeError, match="Unexpected Redfin response shape"):
        _client._extract_rss_json(truncated)
