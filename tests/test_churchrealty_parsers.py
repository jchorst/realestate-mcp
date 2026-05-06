"""Tests for the HTML parsers with minimal hand-crafted fixtures."""

from __future__ import annotations

import pytest

from realestate_mcp.servers.churchrealty import _client

# ---------- HTML fixture builders ----------


def _index_card(
    *,
    slug: str = "church-property-for-sale-houston-tx-10355-mills-road",
    street: str = "10355 Mills Road",
    addr2: str = "Houston, TX 77070",
    agent: str = "Vince Elder",
    phone: str = "832-573-1936",
    img_src: str = "https://www.churchrealty.com/wp-content/uploads/img.jpg",
) -> str:
    return f"""
<div class="property_wrap">
  <div class="col1">
    <div class="featured_image">
      <img decoding="async" src="{img_src}"/>
      <div class="sri-listing">
        <img src="https://www.churchrealty.com/wp-content/uploads/logo.png"/>
      </div>
    </div>
    <div class="col_content">
      <p>{street}</p>
      <p>{addr2}</p>
      <p>Agent : {agent}</p>
      <p>Phone : {phone}</p>
    </div>
    <p class="prop_button">
      <a href="https://www.churchrealty.com/property/{slug}/">View Details</a>
    </p>
  </div>
</div>
"""


def _index_html(cards_html: str) -> str:
    return f"<html><body>{cards_html}</body></html>"


def _detail_html(
    *,
    slug: str = "church-or-school-property-for-sale-humble-tx-600-charles-street",
    h1: str = "Church or School Property For Sale Humble TX",
    h3: str = "Adjacent to the new Humble ISD stadium!",
    street: str = "600 Charles Street",
    addr2: str = "Humble, TX 77338",
    land_area: str = "Land Area: 4.52 acres",
    price: str = "Price: $3,900,000",
    building: str = "Building: 51,325 sqft",
    agent: str = "Agent : Bob Allen",
    phone: str = "Phone: 281-540-2008 ext 2",
    email: str = "Email: BobA@churchrealty.com",
    gallery_imgs: list[str] | None = None,
) -> str:
    if gallery_imgs is None:
        gallery_imgs = [
            "https://www.churchrealty.com/wp-content/uploads/img1.jpg",
            "https://www.churchrealty.com/wp-content/uploads/img2.jpg",
        ]
    gallery_html = "".join(
        f'<img src="{src}"/>' for src in gallery_imgs
    )
    return f"""
<html><body>
<div class="property_wrap">
  <div class="property_top_area"><h1>{h1}</h1></div>
  <div class="property_item_content">
    <h3>{h3}</h3>
    <p>{street}</p>
    <p>{addr2}</p>
    <p>{land_area}</p>
    <p>{price}</p>
    <p>{building}</p>
    <p>{agent}</p>
    <p>{phone}</p>
    <p>{email}</p>
  </div>
</div>
<div class="property_gallery_images">
  {gallery_html}
</div>
</body></html>
"""


# ---------- _parse_index_page ----------


def test_parse_index_page_basic():
    html = _index_html(_index_card())
    cards = _client._parse_index_page(html)
    assert len(cards) == 1
    c = cards[0]
    assert c.listing_id == "church-property-for-sale-houston-tx-10355-mills-road"
    assert c.url == "https://www.churchrealty.com/property/church-property-for-sale-houston-tx-10355-mills-road/"
    assert c.name == "10355 Mills Road"
    assert c.address == "10355 Mills Road"
    assert c.city == "Houston"
    assert c.state == "TX"
    assert c.zip == "77070"
    assert c.listing_type == "For Sale"
    assert c.image_url == "https://www.churchrealty.com/wp-content/uploads/img.jpg"
    assert c.price is None


def test_parse_index_page_for_lease():
    html = _index_html(
        _index_card(
            slug="multi-use-space-for-lease-arlington-tx-7000-matlock-road",
            street="7000 Matlock Road",
            addr2="Arlington, TX 76002",
        )
    )
    cards = _client._parse_index_page(html)
    assert cards[0].listing_type == "For Lease"
    assert cards[0].city == "Arlington"


def test_parse_index_page_multiple_cards():
    two_cards = (
        _index_card(
            slug="church-property-for-sale-houston-tx-10355-mills-road",
            street="10355 Mills Road",
        )
        + _index_card(
            slug="church-property-for-sale-fort-worth-tx-3321-cleburne-road",
            street="3321 Cleburne Road",
            addr2="Fort Worth, TX 76110",
        )
    )
    html = _index_html(two_cards)
    cards = _client._parse_index_page(html)
    assert len(cards) == 2
    assert cards[0].city == "Houston"
    assert cards[1].city == "Fort Worth"


def test_parse_index_page_image_excludes_logo():
    """The first img in featured_image should be the property photo, not the logo."""
    html = _index_html(_index_card(img_src="https://www.churchrealty.com/wp-content/uploads/property.jpg"))
    cards = _client._parse_index_page(html)
    assert cards[0].image_url == "https://www.churchrealty.com/wp-content/uploads/property.jpg"


def test_parse_index_page_missing_cards_raises():
    with pytest.raises(RuntimeError, match="Unexpected Church Realty response shape"):
        _client._parse_index_page("<html><body><p>No listings today.</p></body></html>")


def test_parse_index_page_skips_card_without_link():
    no_link_card = """
<div class="property_wrap">
  <div class="col1">
    <div class="col_content"><p>123 Test St</p><p>Dallas, TX 75001</p></div>
  </div>
</div>
"""
    html = _index_html(no_link_card + _index_card())
    cards = _client._parse_index_page(html)
    assert len(cards) == 1


def test_parse_index_page_to_dict_shape():
    html = _index_html(_index_card())
    d = _client._parse_index_page(html)[0].to_dict()
    for key in ("listing_id", "url", "name", "address", "city", "state", "zip",
                "price", "listing_type", "image_url"):
        assert key in d


# ---------- _parse_detail_page ----------


HUMBLE_SLUG = "church-or-school-property-for-sale-humble-tx-600-charles-street"


def test_parse_detail_page_basic():
    html = _detail_html()
    d = _client._parse_detail_page(html, HUMBLE_SLUG)
    assert d.listing_id == HUMBLE_SLUG
    assert d.url == f"https://www.churchrealty.com/property/{HUMBLE_SLUG}/"
    assert d.name == "Church or School Property For Sale Humble TX"
    assert d.description == "Adjacent to the new Humble ISD stadium!"
    assert d.address == "600 Charles Street"
    assert d.city == "Humble"
    assert d.state == "TX"
    assert d.zip == "77338"
    assert d.price == 3900000.0
    assert d.listing_type == "For Sale"
    assert d.building_sqft == 51325
    assert d.lot_acres == pytest.approx(4.52)
    assert d.year_built is None
    assert d.agent_name == "Bob Allen"
    assert "281-540-2008" in (d.agent_phone or "")
    assert len(d.image_urls) == 2


def test_parse_detail_page_for_lease_slug():
    html = _detail_html(
        slug="multi-use-space-for-lease-arlington-tx-7000-matlock-road",
        h1="Multi-Use Space For Lease Arlington TX",
    )
    d = _client._parse_detail_page(html, "multi-use-space-for-lease-arlington-tx-7000-matlock-road")
    assert d.listing_type == "For Lease"


def test_parse_detail_page_price_none_on_call_agent():
    html = _detail_html(price="Price: Please call agent for price")
    d = _client._parse_detail_page(html, "some-property-for-lease")
    assert d.price is None


def test_parse_detail_page_no_h3_description_is_none():
    html = _detail_html(h3="").replace("<h3></h3>", "")
    d = _client._parse_detail_page(html, "some-slug-for-sale")
    assert d.description is None


def test_parse_detail_page_gallery_deduplicates():
    """The slider renders each image twice; deduplication must keep each once."""
    duplicate_imgs = [
        "https://www.churchrealty.com/wp-content/uploads/img1.jpg",
        "https://www.churchrealty.com/wp-content/uploads/img2.jpg",
        "https://www.churchrealty.com/wp-content/uploads/img1.jpg",
        "https://www.churchrealty.com/wp-content/uploads/img2.jpg",
    ]
    html = _detail_html(gallery_imgs=duplicate_imgs)
    d = _client._parse_detail_page(html, "some-slug-for-sale")
    assert d.image_urls == [
        "https://www.churchrealty.com/wp-content/uploads/img1.jpg",
        "https://www.churchrealty.com/wp-content/uploads/img2.jpg",
    ]


def test_parse_detail_page_no_gallery_empty_image_urls():
    html = _detail_html(gallery_imgs=[]).replace(
        '<div class="property_gallery_images">\n  \n</div>', ""
    )
    d = _client._parse_detail_page(html, "some-slug-for-sale")
    assert d.image_urls == []


def test_parse_detail_page_missing_wrap_raises():
    with pytest.raises(RuntimeError, match="Unexpected Church Realty response shape"):
        _client._parse_detail_page("<html><body><p>oops</p></body></html>", "some-slug")


def test_parse_detail_page_missing_item_content_raises():
    html = """
<html><body>
<div class="property_wrap">
  <div class="property_top_area"><h1>Test</h1></div>
</div>
</body></html>
"""
    with pytest.raises(RuntimeError, match="Unexpected Church Realty response shape"):
        _client._parse_detail_page(html, "some-slug")


def test_parse_detail_page_to_dict_shape():
    html = _detail_html()
    d = _client._parse_detail_page(
        html, "church-or-school-property-for-sale-humble-tx-600-charles-street"
    ).to_dict()
    for key in ("listing_id", "url", "name", "address", "city", "state", "zip",
                "price", "listing_type", "description", "building_sqft", "lot_acres",
                "year_built", "image_urls", "agent_name", "agent_phone"):
        assert key in d
