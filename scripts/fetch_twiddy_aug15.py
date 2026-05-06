"""Fetch Twiddy 7+ BR rentals across north OBX, get Aug 15 2026 weekly rates,
filter to <= $11,000, dump to JSON for spreadsheet ingestion.
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from realestate_mcp.servers.twiddy import _client  # noqa: E402

TOWNS = ["corolla", "4x4", "duck", "southern-shores", "kill-devil-hills", "nags-head"]
TARGET_ARRIVE = "2026-08-15"
MAX_PRICE = 11000
OUT = Path(r"C:\Users\jchorst\Desktop\twiddy_aug15_2026.json")


def fetch_one(listing: dict) -> dict | None:
    try:
        d = _client.get_rental_details(listing["listing_id"])
    except Exception as e:
        print(f"  ! {listing['listing_id']} {listing.get('name')}: {e}")
        return None

    aug15 = next(
        (w for w in (d.get("weekly_rates") or []) if w.get("arrive") == TARGET_ARRIVE),
        None,
    )
    if not aug15 or not aug15.get("is_available"):
        return None

    price = aug15.get("weekly_rate")
    if price is None:
        return None

    return {
        **listing,
        "bathrooms_full": d.get("bathrooms_full"),
        "bathrooms_half": d.get("bathrooms_half"),
        "weekly_rate_aug15": price,
        "weekly_rate_display": aug15.get("week_content"),
    }


def main() -> None:
    all_listings: list[dict] = []
    for town in TOWNS:
        try:
            r = _client.search_rentals(town=town, min_bedrooms=7, max_results=200)
        except Exception as e:
            print(f"[{town}] FAILED: {e}")
            continue
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
            if i % 25 == 0:
                msg = f"  ...{i}/{len(all_listings)} fetched, {len(results)} w/ Aug 15 so far"
                print(msg)

    in_budget = [r for r in results if r["weekly_rate_aug15"] <= MAX_PRICE]
    in_budget.sort(key=lambda r: r["weekly_rate_aug15"])

    print()
    print(f"Listings with Aug 15 2026 availability: {len(results)}")
    print(f"Of those, in budget (<= ${MAX_PRICE:,}): {len(in_budget)}")
    print()
    for r in in_budget:
        baths_full = r.get("bathrooms_full")
        baths_half = r.get("bathrooms_half")
        baths_str = f"{baths_full}/{baths_half}ba" if baths_full is not None else "?ba"
        sleeps = r.get("sleeps") or "?"
        line = (
            f"  ${r['weekly_rate_aug15']:>8,.0f} | "
            f"{r['town']:18s} | {r['bedrooms']}br/{baths_str} | "
            f"sleeps {sleeps!s:>3} | OF={r.get('oceanfront')} | {r['name']}"
        )
        print(line)

    OUT.write_text(json.dumps(in_budget, indent=2))
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
