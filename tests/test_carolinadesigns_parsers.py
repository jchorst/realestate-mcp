"""Tests for the Carolina Designs JSON parsers with hand-crafted fixtures."""

from __future__ import annotations

import pytest

from realestate_mcp.servers.carolinadesigns import _client

# ---------- helpers for building minimal fixtures ----------


def _search_payload(results: list[dict], title: str = "Corolla Vacation Rentals") -> dict:
    """Build a minimal search results payload."""
    return {
        "Results": results,
        "SearchArgs": {"SearchType": "32"},
        "SearchDescription": f" ({len(results)} results)",
        "Title": title,
        "ZeroResultsText": None,
    }


def _search_item(
    *,
    propid: str = "161",
    propname: str = "OCEAN SOL",
    bedrooms: int = 15,
    baths: str = "15/2",
    prop_url: str = "/corolla-vacation-rental/161-ocean-sol/",
    display_location: str = "290 yds from Beach Access",
    display_sub: str = "Whalehead in Corolla",
    image_url: str = "https://img.example/ocean-sol.jpg",
    pet_friendly: bool = True,
    private_pool: bool = True,
) -> dict:
    return {
        "Propid": propid,
        "Propname": propname,
        "Bedrooms": bedrooms,
        "Baths": baths,
        "PropURL": prop_url,
        "DisplayLocation": display_location,
        "DisplaySub": display_sub,
        "ImageURL": image_url,
        "PetFriendly": pet_friendly,
        "PrivatePool": private_pool,
        "WeeklyRate": None,
        "TopAmenities": ["Pool", "Hot Tub"],
    }


def _detail_payload(
    *,
    propid: str = "161",
    propname: str = "OCEAN SOL",
    area: str = "Corolla",
    num_bedrooms: str = "15",
    bathroominfo: list[str] | None = None,
    sleeps: str = "30",
    description: str = "<p>Great house</p>",
    sidebar: list[dict] | None = None,
    pics_large: list[dict] | None = None,
    weeks1: list[dict] | None = None,
    min_price: int = 3690,
    max_price: int = 9690,
    canonical_url: str = "https://www.carolinadesigns.com/corolla-vacation-rental/161-ocean-sol/",
) -> dict:
    if bathroominfo is None:
        bathroominfo = ["Full Bathrooms: 15", "Half Bathrooms 2"]
    if sidebar is None:
        sidebar = [
            {"Title": "Overview", "Items": ["15 Bedrooms (15 Private Baths)", "Elevator"]},
            {"Title": "Exterior", "Items": ["Private Pool", "Hot Tub"]},
        ]
    if pics_large is None:
        pics_large = [
            {"ImgDesc": "Front", "ImgUrl": "https://img.example/front.jpg"},
            {"ImgDesc": "Pool", "ImgUrl": "https://img.example/pool.jpg"},
        ]
    if weeks1 is None:
        weeks1 = [
            {
                "ArrivalDate": "5/9/2026",
                "Rate": "$4,690.00",
                "CostPerNight": "$670.00",
                "Orate": "$6,990.00",
                "BookType": "NORM",
                "PetFeeDefaultChecked": False,
            },
            {
                "ArrivalDate": "5/23/2026",
                "Rate": "$0.00",
                "CostPerNight": "Booked",
                "Orate": "Booked",
                "BookType": "",
                "PetFeeDefaultChecked": False,
            },
        ]
    return {
        "Propid": propid,
        "Propname": propname,
        "Area": area,
        "NumBedrooms": num_bedrooms,
        "NumBathrooms": "15.20",
        "Bathroominfo": bathroominfo,
        "Sleeps": sleeps,
        "Description": description,
        "Sidebar": sidebar,
        "PicsLarge": pics_large,
        "Weeks1CurrAvail": weeks1,
        "Weeks2CurrAvail": None,
        "MinPrice": min_price,
        "MaxPrice": max_price,
        "CanonicalUrl": canonical_url,
    }


# ---------- _parse_search_results ----------


def test_parse_search_results_basic():
    payload = _search_payload([_search_item()])
    listings = _client._parse_search_results(payload, "corolla")
    assert len(listings) == 1
    li = listings[0]
    assert li.listing_id == "161"
    assert li.name == "OCEAN SOL"
    assert li.bedrooms == 15
    assert li.bathrooms_full == 15
    assert li.bathrooms_half == 2
    assert li.town == "corolla"
    assert li.location == "290 yds from Beach Access"
    assert li.subdivision == "Whalehead in Corolla"
    assert li.image_url == "https://img.example/ocean-sol.jpg"
    assert li.pet_friendly is True
    assert li.private_pool is True
    assert "carolinadesigns.com" in li.url


def test_parse_search_results_prepends_base_url_to_relative_prop_url():
    item = _search_item(prop_url="/corolla-vacation-rental/161-ocean-sol/")
    payload = _search_payload([item])
    listings = _client._parse_search_results(payload, "corolla")
    assert listings[0].url == "https://www.carolinadesigns.com/corolla-vacation-rental/161-ocean-sol/"


def test_parse_search_results_skips_items_without_propid():
    bad = _search_item(propid="")
    good = _search_item(propid="200", propname="GOOD HOUSE")
    payload = _search_payload([bad, good])
    listings = _client._parse_search_results(payload, "corolla")
    assert len(listings) == 1
    assert listings[0].listing_id == "200"


def test_parse_search_results_raises_on_missing_results_key():
    with pytest.raises(RuntimeError, match="Unexpected Carolina Designs response shape"):
        _client._parse_search_results({"wrong": "structure"}, "corolla")


def test_parse_search_results_multiple_listings():
    items = [_search_item(propid=str(i), propname=f"HOUSE {i}", bedrooms=i + 3) for i in range(5)]
    payload = _search_payload(items)
    listings = _client._parse_search_results(payload, "duck")
    assert len(listings) == 5
    assert listings[2].bedrooms == 5


def test_parse_search_results_empty_results():
    payload = _search_payload([])
    listings = _client._parse_search_results(payload, "nags-head")
    assert listings == []


# ---------- _parse_rental_details ----------


def test_parse_rental_details_basic():
    payload = _detail_payload()
    d = _client._parse_rental_details(payload, "161")
    assert d.listing_id == "161"
    assert d.name == "OCEAN SOL"
    assert d.town == "corolla"
    assert d.bedrooms == 15
    assert d.bathrooms_full == 15
    assert d.bathrooms_half == 2
    assert d.sleeps == 30
    assert d.description == "Great house"
    assert d.min_price == 3690
    assert d.max_price == 9690
    assert d.url == "https://www.carolinadesigns.com/corolla-vacation-rental/161-ocean-sol/"


def test_parse_rental_details_amenities_from_sidebar():
    payload = _detail_payload(
        sidebar=[
            {"Title": "Overview", "Items": ["15 Bedrooms", "Elevator"]},
            {"Title": "Exterior", "Items": ["Private Pool", "Hot Tub"]},
        ]
    )
    d = _client._parse_rental_details(payload, "161")
    assert "15 Bedrooms" in d.amenities
    assert "Elevator" in d.amenities
    assert "Private Pool" in d.amenities
    assert "Hot Tub" in d.amenities


def test_parse_rental_details_image_urls():
    payload = _detail_payload(
        pics_large=[
            {"ImgDesc": "Front", "ImgUrl": "https://img.example/front.jpg"},
            {"ImgDesc": "Pool", "ImgUrl": "https://img.example/pool.jpg"},
        ]
    )
    d = _client._parse_rental_details(payload, "161")
    assert d.image_urls == [
        "https://img.example/front.jpg",
        "https://img.example/pool.jpg",
    ]


def test_parse_rental_details_weekly_rates():
    payload = _detail_payload()
    d = _client._parse_rental_details(payload, "161")
    assert len(d.weekly_rates) == 2
    available = [r for r in d.weekly_rates if r["book_type"] == "NORM"]
    assert len(available) == 1
    assert available[0]["arrival_date"] == "5/9/2026"
    assert available[0]["weekly_rate"] == "$4,690.00"
    assert available[0]["nightly_rate"] == "$670.00"
    # Booked week has no weekly_rate
    booked = [r for r in d.weekly_rates if not r["book_type"]]
    assert len(booked) == 1
    assert booked[0]["weekly_rate"] is None


def test_parse_rental_details_raises_on_missing_propid():
    with pytest.raises(RuntimeError, match="Unexpected Carolina Designs response shape"):
        _client._parse_rental_details({"wrong": "structure"}, "161")


def test_parse_rental_details_handles_missing_bathroominfo():
    payload = _detail_payload(bathroominfo=None)
    payload["Bathroominfo"] = None
    d = _client._parse_rental_details(payload, "161")
    assert d.bathrooms_full is None
    assert d.bathrooms_half is None


def test_parse_rental_details_strips_html_from_description():
    payload = _detail_payload(description="<article><h3>Overview</h3><p>Great house</p></article>")
    d = _client._parse_rental_details(payload, "161")
    assert "<" not in d.description
    assert "Overview" in d.description
    assert "Great house" in d.description


def test_parse_rental_details_fallback_url_when_no_canonical():
    payload = _detail_payload()
    payload["CanonicalUrl"] = None
    d = _client._parse_rental_details(payload, "161")
    assert "/property-detail-page/161" in d.url
