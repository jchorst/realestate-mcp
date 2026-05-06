"""Tests for Twiddy JSON parsers with hand-crafted minimal fixtures."""

from __future__ import annotations

import pytest

from realestate_mcp.servers.twiddy import _client

# ---------- minimal fixture builders ----------


def _search_payload(results: list[dict]) -> dict:
    return {"isSameDayArrival": False, "results": results}


def _search_item(
    *,
    property_id: int = 5744,
    property_name: str = "Station One",
    property_url: str = "/outer-banks/corolla/pine-island/rentals/station-one/",
    town: str = "Corolla",
    bedrooms: str = "10 beds",
    distance_to_beach: str = "Oceanfront",
    images: list[str] | None = None,
    amenity_items: list[dict] | None = None,
) -> dict:
    if images is None:
        images = ["392559?v=abc123"]
    if amenity_items is None:
        amenity_items = [{"label": "10 bedrooms", "description": "(Sleeps 25)", "match": False}]
    return {
        "propertyId": property_id,
        "propertyName": property_name,
        "propertyNumber": "E400",
        "propertyUrl": property_url,
        "rating": None,
        "town": town,
        "bedrooms": bedrooms,
        "distanceToBeach": distance_to_beach,
        "locationItems": [{"label": "Corolla, NC", "description": None, "match": True}],
        "amenityItems": amenity_items,
        "checkInItem": {"label": "Sunday check-in", "description": None, "match": False},
        "saves": 0,
        "lat": 36.23,
        "lon": -75.77,
        "isSaved": False,
        "badges": [],
        "images": images,
        "availabilityBadges": [],
        "price": "Available from $15,000",
        "isAvailable": True,
    }


def _info_payload(
    *,
    property_id: int = 5744,
    name: str = "Station One",
    city: str = "Corolla",
    full_url: str = "/outer-banks/corolla/pine-island/rentals/station-one/",
    neighborhood: str = "Pine Island",
    location: str = "Oceanfront",
    description: str = "A great oceanfront home.",
    exterior_image: str = "https://www.twiddy.com/rns/unitimages.twd/e400.jpg",
) -> dict:
    return {
        "propertyID": property_id,
        "unitNumber": "E400",
        "name": name,
        "streetAddress1": "103 Station One",
        "city": city,
        "state": "NC",
        "zip": "27927",
        "description": description,
        "neighborhood": neighborhood,
        "location": location,
        "fullUrl": full_url,
        "exteriorImage": exterior_image,
        "bedrooms": 10,
        "fullBaths": 9,
        "partialBaths": 1,
        "totalBaths": 10,
        "distanceToBeach": None,
    }


def _amenities_payload(
    *,
    bathrooms_summary: str = "9 Full 1 Half",
    bathrooms_total: int = 10,
    bedrooms: int = 10,
    sleeps_count: int = 25,
    featured_amenities: list[dict] | None = None,
) -> dict:
    if featured_amenities is None:
        featured_amenities = [
            {"displayLabel": "Private Pool", "iconName": "fa-pool"},
            {"displayLabel": "Hot Tub", "iconName": "fa-hot-tub"},
            {"displayLabel": "Pets Allowed", "iconName": "fa-dog"},
        ]
    return {
        "sectionModel": {
            "featuredAmenities": featured_amenities,
            "amenityCategories": [],
        },
        "bathroomsSummary": bathrooms_summary,
        "bathroomsTotal": bathrooms_total,
        "bedrooms": bedrooms,
        "sleepsCount": sleeps_count,
    }


def _calendar_payload(
    *,
    weeks: list[dict] | None = None,
) -> dict:
    if weeks is None:
        weeks = [
            {
                "arrive": "2026-05-03T00:00:00",
                "depart": "2026-05-10T00:00:00",
                "weekContent": "Weekly Rate $9,650",
                "weeklyRate": 9650.0,
                "isAvailable": True,
            },
            {
                "arrive": "2026-05-10T00:00:00",
                "depart": "2026-05-17T00:00:00",
                "weekContent": "Booked",
                "weeklyRate": 11000.0,
                "isAvailable": False,
            },
        ]
    return {
        "calculatorWeeklyRate": 0,
        "amenityYear": 2026,
        "availabilityYears": [
            {
                "year": 2026,
                "selected": True,
                "months": [
                    {
                        "monthTitle": "May 2026",
                        "monthNum": 5,
                        "year": 2026,
                        "month": "May",
                        "weeks": weeks,
                    }
                ],
            }
        ],
    }


# ---------- _parse_search_results ----------


def test_parse_search_results_basic():
    payload = _search_payload([_search_item()])
    listings = _client._parse_search_results(payload, "corolla")
    assert len(listings) == 1
    li = listings[0]
    assert li.listing_id == 5744
    assert li.name == "Station One"
    assert li.bedrooms == 10
    assert li.town == "Corolla"
    assert li.neighborhood == "Pine Island"
    assert li.distance_to_beach == "Oceanfront"
    assert li.oceanfront is True
    assert li.image_url == "https://www.twiddy.com/property-images/392559?v=abc123"
    assert li.sleeps == 25
    assert "twiddy.com" in li.url


def test_parse_search_results_non_oceanfront():
    item = _search_item(distance_to_beach="Semi-Oceanfront")
    payload = _search_payload([item])
    listings = _client._parse_search_results(payload, "corolla")
    assert listings[0].oceanfront is False
    assert listings[0].distance_to_beach == "Semi-Oceanfront"


def test_parse_search_results_no_images():
    item = _search_item(images=[])
    payload = _search_payload([item])
    listings = _client._parse_search_results(payload, "corolla")
    assert listings[0].image_url is None


def test_parse_search_results_skips_items_without_property_id():
    bad = _search_item(property_id=0)
    bad["propertyId"] = None
    good = _search_item(property_id=999, property_name="Good House")
    payload = _search_payload([bad, good])
    listings = _client._parse_search_results(payload, "corolla")
    assert len(listings) == 1
    assert listings[0].listing_id == 999


def test_parse_search_results_raises_on_missing_results_key():
    with pytest.raises(RuntimeError, match="Unexpected Twiddy response shape"):
        _client._parse_search_results({"wrong": "key"}, "corolla")


def test_parse_search_results_multiple_listings():
    items = [_search_item(property_id=i + 100, property_name=f"House {i}") for i in range(4)]
    payload = _search_payload(items)
    listings = _client._parse_search_results(payload, "corolla")
    assert len(listings) == 4


def test_parse_search_results_empty_results():
    payload = _search_payload([])
    listings = _client._parse_search_results(payload, "duck")
    assert listings == []


def test_parse_search_results_sleeps_from_amenity_items():
    item = _search_item(
        amenity_items=[{"label": "8 bedrooms", "description": "(Sleeps 20)", "match": False}]
    )
    payload = _search_payload([item])
    listings = _client._parse_search_results(payload, "corolla")
    assert listings[0].sleeps == 20


def test_parse_search_results_no_sleeps_when_no_amenity_items():
    item = _search_item(amenity_items=[])
    payload = _search_payload([item])
    listings = _client._parse_search_results(payload, "corolla")
    assert listings[0].sleeps is None


# ---------- _parse_rental_details ----------


def test_parse_rental_details_basic():
    info = _info_payload()
    amen = _amenities_payload()
    cal = _calendar_payload()
    d = _client._parse_rental_details(info, amen, cal, 5744)
    assert d.listing_id == 5744
    assert d.name == "Station One"
    assert d.town == "corolla"
    assert d.neighborhood == "Pine Island"
    assert d.bedrooms == 10
    assert d.bathrooms_full == 9
    assert d.bathrooms_half == 1
    assert d.sleeps == 25
    assert d.description == "A great oceanfront home."
    assert "twiddy.com" in d.url


def test_parse_rental_details_amenities_from_featured():
    amen = _amenities_payload(
        featured_amenities=[
            {"displayLabel": "Private Pool"},
            {"displayLabel": "Hot Tub"},
            {"displayLabel": "Pets Allowed"},
        ]
    )
    d = _client._parse_rental_details(_info_payload(), amen, _calendar_payload(), 5744)
    assert "Private Pool" in d.amenities
    assert "Hot Tub" in d.amenities
    assert "Pets Allowed" in d.amenities


def test_parse_rental_details_image_urls_from_exterior():
    info = _info_payload(exterior_image="https://www.twiddy.com/rns/unitimages.twd/e400.jpg")
    d = _client._parse_rental_details(info, _amenities_payload(), _calendar_payload(), 5744)
    assert d.image_urls == ["https://www.twiddy.com/rns/unitimages.twd/e400.jpg"]


def test_parse_rental_details_no_exterior_image():
    info = _info_payload(exterior_image=None)
    info["exteriorImage"] = None
    d = _client._parse_rental_details(info, _amenities_payload(), _calendar_payload(), 5744)
    assert d.image_urls == []


def test_parse_rental_details_weekly_rates():
    cal = _calendar_payload()
    d = _client._parse_rental_details(_info_payload(), _amenities_payload(), cal, 5744)
    assert len(d.weekly_rates) == 2
    available = [r for r in d.weekly_rates if r["is_available"]]
    booked = [r for r in d.weekly_rates if not r["is_available"]]
    assert len(available) == 1
    assert available[0]["arrive"] == "2026-05-03"
    assert available[0]["weekly_rate"] == 9650.0
    assert len(booked) == 1
    assert booked[0]["week_content"] == "Booked"


def test_parse_rental_details_raises_on_missing_property_id():
    info = _info_payload()
    del info["propertyID"]
    with pytest.raises(RuntimeError, match="Unexpected Twiddy response shape"):
        _client._parse_rental_details(info, _amenities_payload(), _calendar_payload(), 5744)


def test_parse_rental_details_week_content_strips_html():
    cal = _calendar_payload(
        weeks=[
            {
                "arrive": "2026-06-07T00:00:00",
                "depart": "2026-06-14T00:00:00",
                "weekContent": (
                    "Weekly rate <s>$27,995</s>"
                    " <strong class=\"text-orange\">$24,995</strong>"
                ),
                "weeklyRate": 24995.0,
                "isAvailable": True,
            }
        ]
    )
    d = _client._parse_rental_details(_info_payload(), _amenities_payload(), cal, 5744)
    assert "<" not in d.weekly_rates[0]["week_content"]
    assert "$24,995" in d.weekly_rates[0]["week_content"]


def test_parse_rental_details_full_url_prepends_base():
    info = _info_payload(full_url="/outer-banks/corolla/pine-island/rentals/station-one/")
    d = _client._parse_rental_details(info, _amenities_payload(), _calendar_payload(), 5744)
    assert d.url == "https://www.twiddy.com/outer-banks/corolla/pine-island/rentals/station-one/"


def test_parse_rental_details_empty_calendar():
    cal = {"availabilityYears": []}
    d = _client._parse_rental_details(_info_payload(), _amenities_payload(), cal, 5744)
    assert d.weekly_rates == []
