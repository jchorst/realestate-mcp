# ruff: noqa: E501
"""Fetch Carolina Designs 7+ BR rentals across north OBX, get Aug 15 2026 weekly rates,
filter to <= $11,000, dump to JSON for spreadsheet ingestion.
"""
from __future__ import annotations

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from realestate_mcp.servers.carolinadesigns import _client  # noqa: E402

TOWNS = ["corolla", "duck", "southern-shores", "kitty-hawk", "kill-devil-hills", "nags-head"]
TARGET_DATE = "8/15/2026"
MAX_PRICE = 11000
OUT = Path(r"C:\Users\jchorst\Desktop\carolinadesigns_aug15_2026.json")


def parse_price(s: str | None) -> float | None:
    if not s:
        return None
    m = re.search(r"\$([\d,]+(?:\.\d+)?)", s)
    return float(m.group(1).replace(",", "")) if m else None


def fetch_one(listing: dict) -> dict | None:
    try:
        d = _client.get_rental_details(listing["listing_id"])
    except Exception as e:
        print(f"  ! {listing['listing_id']} {listing['name']}: {e}")
        return None

    aug15 = next((w for w in d.get("weekly_rates") or [] if w.get("arrival_date") == TARGET_DATE), None)
    if not aug15:
        return None

    price = parse_price(aug15.get("weekly_rate"))
    if price is None:
        return None

    sleeps = d.get("sleeps")
    return {
        **listing,
        "sleeps": sleeps,
        "weekly_rate_aug15": price,
        "weekly_rate_display": aug15.get("weekly_rate"),
        "book_type": aug15.get("book_type"),
    }


def main() -> None:
    all_listings: list[dict] = []
    for town in TOWNS:
        r = _client.search_rentals(town=town, min_bedrooms=7, max_results=100)
        for li in r["listings"]:
            li_dict = li if isinstance(li, dict) else li.to_dict()
            all_listings.append(li_dict)
        print(f"[{town}] {r['total_returned']} listings with 7+ BR")
    print(f"Total: {len(all_listings)} listings to fetch details for")

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(fetch_one, li): li for li in all_listings}
        for i, fut in enumerate(as_completed(futures), 1):
            r = fut.result()
            if r:
                results.append(r)
            if i % 20 == 0:
                print(f"  ...{i}/{len(all_listings)} fetched, {len(results)} with Aug 15 data so far")

    in_budget = [r for r in results if r["weekly_rate_aug15"] <= MAX_PRICE]
    in_budget.sort(key=lambda r: r["weekly_rate_aug15"])

    print()
    print(f"Listings with Aug 15 2026 availability: {len(results)}")
    print(f"Of those, in budget (<= ${MAX_PRICE:,}): {len(in_budget)}")
    print()
    for r in in_budget:
        print(f"  ${r['weekly_rate_aug15']:>8,.0f} | {r['town']:20s} | {r['bedrooms']}br/{r['bathrooms_full']}ba | "
              f"sleeps {r.get('sleeps') or '?':>3} | {r['name']}")

    OUT.write_text(json.dumps(in_budget, indent=2))
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
