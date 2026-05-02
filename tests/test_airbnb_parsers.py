"""Tests for the JSON parsers and result merger."""

from __future__ import annotations

import base64
from typing import Any

import pytest

from realestate_mcp.servers.airbnb import _client


def _make_listing_id(numeric: str) -> str:
    """Encode a numeric ID into Airbnb's base64 demandStayListing format."""
    return base64.b64encode(f"DemandStayListing:{numeric}".encode()).decode()


def _search_payload(listings: list[dict[str, Any]], cursors: list[str] | None = None) -> dict:
    """Build a minimal search payload mimicking Airbnb's response shape."""
    return {
        "niobeClientData": [
            [
                "QueryKey",
                {
                    "data": {
                        "presentation": {
                            "staysSearch": {
                                "results": {
                                    "searchResults": listings,
                                    "paginationInfo": {
                                        "pageCursors": cursors or ["cursor0", "cursor1"]
                                    },
                                }
                            }
                        }
                    }
                },
            ]
        ]
    }


def _listing(
    *,
    id_: str = "100",
    title: str = "Home in Asheville",
    subtitle: str = "Cozy Cabin",
    bedrooms: str = "3 bedrooms",
    beds: str = "5 beds",
    baths: str = "2.5 baths",
    price: str = "$1,000",
    rating: str = "4.9 (123)",
    lat: float = 35.5,
    lng: float = -82.5,
) -> dict:
    primary = []
    for body in (bedrooms, beds, baths):
        if body is not None:
            primary.append({"body": body})
    return {
        "demandStayListing": {
            "id": _make_listing_id(id_),
            "location": {"coordinate": {"latitude": lat, "longitude": lng}},
        },
        "structuredContent": {"primaryLine": primary},
        "structuredDisplayPrice": {
            "primaryLine": {"discountedPrice": price, "qualifier": "for 5 nights"}
        },
        "title": title,
        "subtitle": subtitle,
        "avgRatingLocalized": rating,
        "contextualPictures": [{"picture": "https://img.example/1.jpg"}],
    }


# ---------- _parse_search_results ----------


def test_parse_search_results_basic():
    payload = _search_payload([_listing()])
    listings, cursors = _client._parse_search_results(payload, "2026-01-01", "2026-01-06", 5)
    assert len(listings) == 1
    li = listings[0]
    assert li.listing_id == "100"
    assert li.url == "https://www.airbnb.com/rooms/100"
    assert li.name == "Cozy Cabin"
    assert li.property_type == "Home in Asheville"
    assert li.bedrooms == 3
    assert li.beds == 5
    assert li.bathrooms == 2.5
    assert li.latitude == 35.5
    assert li.longitude == -82.5
    assert li.rating == 4.9
    assert li.review_count == 123
    assert li.check_in == "2026-01-01"
    assert li.check_out == "2026-01-06"
    assert li.nights == 5
    assert li.total_price == 1000.0
    assert li.price_currency == "$"
    assert li.image_url == "https://img.example/1.jpg"
    assert cursors == ["cursor0", "cursor1"]


def test_parse_search_results_skips_listings_without_id():
    bad = _listing()
    bad["demandStayListing"]["id"] = None
    good = _listing(id_="200")
    payload = _search_payload([bad, good])
    listings, _ = _client._parse_search_results(payload, "2026-01-01", "2026-01-06", 5)
    assert [li.listing_id for li in listings] == ["200"]


def test_parse_search_results_handles_truncated_primary_line():
    """When Airbnb omits bath info, bathrooms should be None but other fields parse."""
    li = _listing(baths=None)
    payload = _search_payload([li])
    listings, _ = _client._parse_search_results(payload, "2026-01-01", "2026-01-06", 5)
    assert listings[0].bedrooms == 3
    assert listings[0].beds == 5
    assert listings[0].bathrooms is None


def test_parse_search_results_missing_rating():
    li = _listing(rating=None)
    li["avgRatingLocalized"] = None
    payload = _search_payload([li])
    listings, _ = _client._parse_search_results(payload, "2026-01-01", "2026-01-06", 5)
    assert listings[0].rating is None
    assert listings[0].review_count is None


def test_parse_search_results_raises_on_unexpected_shape():
    with pytest.raises(RuntimeError, match="Unexpected Airbnb response shape"):
        _client._parse_search_results({"wrong": "structure"}, "2026-01-01", "2026-01-06", 5)


# ---------- _parse_listing_details ----------


def _details_payload(*, listing_id: str = "9999", **overrides: Any) -> dict:
    sections = [
        {"sectionId": "TITLE_DEFAULT", "section": {"title": overrides.get("title", "Cozy Place")}},
        {
            "sectionId": "DESCRIPTION_DEFAULT",
            "section": {
                "htmlDescription": {
                    "htmlText": overrides.get("desc", "<p>A nice place</p>")
                }
            },
        },
        {
            "sectionId": "AMENITIES_DEFAULT",
            "section": {
                "seeAllAmenitiesGroups": [
                    {
                        "title": "Bathroom",
                        "amenities": [
                            {"title": "Bathtub", "available": True},
                            {"title": "Bidet", "available": False},
                        ],
                    },
                    {
                        "title": "Kitchen",
                        "amenities": [{"title": "Microwave", "available": True}],
                    },
                ]
            },
        },
        {
            "sectionId": "MEET_YOUR_HOST",
            "section": {
                "cardData": {
                    "name": "Kelly",
                    "isSuperhost": True,
                    "isVerified": True,
                    "stats": [
                        {"type": "REVIEW_COUNT", "value": "1,234"},
                        {"type": "OTHER", "value": "irrelevant"},
                    ],
                },
                "about": "I love hosting!",
            },
        },
        {
            "sectionId": "REVIEWS_DEFAULT",
            "section": {
                "overallRating": 4.95,
                "overallCount": 200,
                "isGuestFavorite": True,
                "ratings": [
                    {"label": "Cleanliness", "localizedRating": "5.0"},
                    {"label": "Communication", "localizedRating": "4.9"},
                ],
            },
        },
        {
            "sectionId": "LOCATION_DEFAULT",
            "section": {
                "subtitle": "Asheville, NC",
                "lat": 35.5,
                "lng": -82.5,
            },
        },
        {
            "sectionId": "POLICIES_DEFAULT",
            "section": {
                "houseRules": [
                    {"title": "Check-in after 3 PM"},
                    {"title": "No smoking"},
                    {"title": None},
                ],
                "cancellationPolicyForDisplay": "Free cancellation for 48 hours",
            },
        },
        {
            "sectionId": "BOOK_IT_SIDEBAR",
            "section": {"maxGuestCapacity": 8},
        },
        {
            "sectionId": "SLEEPING_ARRANGEMENT_WITH_IMAGES",
            "section": {
                "arrangementDetails": [
                    {"title": "Bedroom 1", "subtitle": "1 king bed"},
                    {"title": "Bedroom 2", "subtitle": "2 single beds"},
                ]
            },
        },
        {
            "sectionId": "HIGHLIGHTS_DEFAULT",
            "section": {
                "highlights": [
                    {"title": "Top 5%", "subtitle": "Highly rated"},
                    {"title": None, "subtitle": None},
                ]
            },
        },
        {
            "sectionId": "HERO_DEFAULT",
            "section": {
                "previewImages": [
                    {"baseUrl": "https://img.example/a.jpg"},
                    {"baseUrl": "https://img.example/b.jpg"},
                    {"baseUrl": "https://img.example/a.jpg"},  # dup, should dedupe
                ]
            },
        },
    ]
    return {
        "niobeClientData": [
            [
                "Key",
                {
                    "data": {
                        "presentation": {
                            "stayProductDetailPage": {"sections": {"sections": sections}}
                        },
                        "node": {"pdpPresentation": {"mediaTour": {"stops": []}}},
                    }
                },
            ]
        ]
    }


def test_parse_listing_details_full():
    payload = _details_payload()
    d = _client._parse_listing_details(payload, "9999")
    assert d.listing_id == "9999"
    assert d.url == "https://www.airbnb.com/rooms/9999"
    assert d.title == "Cozy Place"
    assert d.description == "A nice place"
    assert d.max_guests == 8
    assert d.sleeping_arrangements == ["Bedroom 1: 1 king bed", "Bedroom 2: 2 single beds"]
    assert d.location_subtitle == "Asheville, NC"
    assert d.latitude == 35.5
    assert d.longitude == -82.5
    assert d.host_name == "Kelly"
    assert d.host_is_superhost is True
    assert d.host_is_verified is True
    assert d.host_about == "I love hosting!"
    assert d.host_review_count == 1234
    assert d.overall_rating == 4.95
    assert d.review_count == 200
    assert d.is_guest_favorite is True
    assert d.rating_breakdown == {"Cleanliness": "5.0", "Communication": "4.9"}
    assert d.amenities == ["Bathtub", "Microwave"]
    assert d.unavailable_amenities == ["Bidet"]
    assert d.house_rules == ["Check-in after 3 PM", "No smoking"]
    assert d.cancellation_policy == "Free cancellation for 48 hours"
    assert d.highlights == [{"title": "Top 5%", "subtitle": "Highly rated"}]
    assert d.image_urls == ["https://img.example/a.jpg", "https://img.example/b.jpg"]


def test_parse_listing_details_falls_back_to_mediaTour():
    """When HERO_DEFAULT.previewImages is empty, mediaTour.stops should populate images."""
    payload = _details_payload()
    sections = payload["niobeClientData"][0][1]["data"]["presentation"][
        "stayProductDetailPage"
    ]["sections"]["sections"]
    for s in sections:
        if s.get("sectionId") == "HERO_DEFAULT":
            s["section"]["previewImages"] = []
    payload["niobeClientData"][0][1]["data"]["node"]["pdpPresentation"]["mediaTour"] = {
        "stops": [
            {"items": [{"image": {"uri": "https://img.example/c.jpg"}}]},
            {"items": [{"image": {"uri": "https://img.example/d.jpg"}}]},
        ]
    }
    d = _client._parse_listing_details(payload, "9999")
    assert d.image_urls == ["https://img.example/c.jpg", "https://img.example/d.jpg"]


def test_parse_listing_details_raises_on_unexpected_shape():
    with pytest.raises(RuntimeError, match="Unexpected Airbnb listing response shape"):
        _client._parse_listing_details({"missing": True}, "9999")


# ---------- merge_search_results ----------


def _result(listings: list[dict], area: str = "Test City") -> dict:
    return {"search_area": area, "total_returned": len(listings), "listings": listings}


def _li_dict(id_: str, total_price: float | None, check_in: str = "2026-07-11") -> dict:
    return {"listing_id": id_, "total_price": total_price, "check_in": check_in}


def test_merge_keeps_cheapest_per_listing():
    a = _result([_li_dict("1", 1500, "2026-07-11"), _li_dict("2", 2000, "2026-07-11")])
    b = _result([_li_dict("1", 1300, "2026-07-12"), _li_dict("2", 2100, "2026-07-12")])
    merged = _client.merge_search_results([a, b], max_results=10)
    by_id = {li["listing_id"]: li for li in merged["listings"]}
    assert by_id["1"]["total_price"] == 1300
    assert by_id["1"]["check_in"] == "2026-07-12"
    assert by_id["2"]["total_price"] == 2000
    assert by_id["2"]["check_in"] == "2026-07-11"


def test_merge_includes_listings_only_in_one_set():
    a = _result([_li_dict("1", 1500), _li_dict("2", 2000)])
    b = _result([_li_dict("3", 1800)])
    merged = _client.merge_search_results([a, b], max_results=10)
    assert {li["listing_id"] for li in merged["listings"]} == {"1", "2", "3"}


def test_merge_sorts_by_total_price_ascending():
    a = _result([_li_dict("1", 2000), _li_dict("2", 800), _li_dict("3", 1500)])
    merged = _client.merge_search_results([a], max_results=10)
    prices = [li["total_price"] for li in merged["listings"]]
    assert prices == [800, 1500, 2000]


def test_merge_puts_none_prices_last():
    a = _result(
        [
            _li_dict("a", None),
            _li_dict("b", 1000),
            _li_dict("c", None),
            _li_dict("d", 500),
        ]
    )
    merged = _client.merge_search_results([a], max_results=10)
    ids = [li["listing_id"] for li in merged["listings"]]
    assert ids[0] == "d"
    assert ids[1] == "b"
    assert set(ids[2:]) == {"a", "c"}


def test_merge_prefers_real_price_over_none():
    a = _result([_li_dict("1", None, "2026-07-11")])
    b = _result([_li_dict("1", 1500, "2026-07-12")])
    merged = _client.merge_search_results([a, b], max_results=10)
    assert merged["listings"][0]["total_price"] == 1500
    assert merged["listings"][0]["check_in"] == "2026-07-12"


def test_merge_caps_at_max_results():
    a = _result([_li_dict(str(i), 100 + i) for i in range(10)])
    merged = _client.merge_search_results([a], max_results=3)
    assert len(merged["listings"]) == 3
    assert merged["total_returned"] == 3


def test_merge_empty():
    merged = _client.merge_search_results([], max_results=10)
    assert merged == {"search_area": "", "total_returned": 0, "listings": []}
