"""Fetch Surf or Sound 7+ BR Hatteras Island rentals for Sat Aug 15 2026,
filter to <= $11,000, dump to JSON for spreadsheet ingestion.

Surf or Sound's search endpoint accepts check_in directly and returns the
weekly rate for that arrival week — no per-listing detail fetch needed.
This is cleaner than Carolina Designs / Twiddy which both required detail fetches.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from realestate_mcp.servers.surforsound import _client  # noqa: E402

VILLAGES = ["rodanthe", "waves", "salvo", "avon", "buxton", "frisco", "hatteras"]
TARGET_CHECKIN = "2026-08-15"
MAX_PRICE = 11000
OUT = Path(r"C:\Users\jchorst\Desktop\surforsound_aug15_2026.json")


def main() -> None:
    all_listings: list[dict] = []
    for village in VILLAGES:
        try:
            r = _client.search_rentals(
                town=village,
                min_bedrooms=7,
                max_results=200,
                check_in=TARGET_CHECKIN,
            )
        except Exception as e:
            print(f"[{village}] FAILED: {e}")
            continue
        for li in r["listings"]:
            li_dict = li if isinstance(li, dict) else li.to_dict()
            li_dict["village"] = village
            all_listings.append(li_dict)
        print(f"[{village}] {r['total_returned']} listings with 7+ BR available Aug 15")

    in_budget = [
        li for li in all_listings
        if li.get("weekly_rate") is not None and li["weekly_rate"] <= MAX_PRICE
    ]
    in_budget.sort(key=lambda li: li["weekly_rate"])

    print()
    print(f"Total 7+ BR with Aug 15 availability: {len(all_listings)}")
    print(f"In budget (<= ${MAX_PRICE:,}): {len(in_budget)}")
    print()
    for li in in_budget:
        print(f"  ${li['weekly_rate']:>8,.0f} | {li['village']:10s} | "
              f"{li['bedrooms']}br/{li.get('bathrooms_full')}+{li.get('bathrooms_half')}ba | "
              f"{li['name']}")

    OUT.write_text(json.dumps(in_budget, indent=2))
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
