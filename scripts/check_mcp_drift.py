"""Drift check for all implemented real-estate MCPs.

For each MCP, run a known-good search → fetch one detail → verify expected fields
are populated. Report PASS / WARN / FAIL per MCP. Exit code 0 on all-pass, 1 on
any FAIL (so CI / cron can detect drift).

Run:
    .venv\\Scripts\\python.exe scripts\\check_mcp_drift.py

Output is structured per-MCP so a human (or Claude) can see at a glance:
- Which MCPs are healthy
- Which MCPs returned results but with missing fields (likely schema drift)
- Which MCPs errored entirely (likely site changed URL pattern, added bot
  protection, or removed the API)
"""

from __future__ import annotations

import sys
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _next_future_saturday(days_out: int = 60) -> date:
    target = date.today() + timedelta(days=days_out)
    return target + timedelta(days=(5 - target.weekday()) % 7)


FUTURE_SAT = _next_future_saturday()
FUTURE_SAT_ISO = FUTURE_SAT.isoformat()
FUTURE_SAT_PLUS_7 = (FUTURE_SAT + timedelta(days=7)).isoformat()


@dataclass
class CheckResult:
    name: str
    status: str  # "PASS" | "WARN" | "FAIL"
    summary: str
    detail: list[str]


def _check_fields(obj: dict, fields: list[str]) -> list[str]:
    """Return list of field names that are missing or empty on obj."""
    missing: list[str] = []
    for f in fields:
        v = obj.get(f)
        # Treat None and "" as missing; 0 and False are valid values for some fields
        if v is None or v == "":
            missing.append(f)
    return missing


def _run(
    name: str,
    *,
    search: Callable[[], dict],
    search_required: list[str],
    details_from: Callable[[dict], Any] | None,
    details_required: list[str],
    results_key: str,
) -> CheckResult:
    detail: list[str] = []
    try:
        r = search()
    except Exception as e:
        return CheckResult(
            name=name,
            status="FAIL",
            summary=f"search() raised {type(e).__name__}: {e}",
            detail=[traceback.format_exc()],
        )

    listings = r.get(results_key) or []
    detail.append(f"search returned {len(listings)} results")
    if not listings:
        return CheckResult(
            name=name,
            status="WARN",
            summary="search returned 0 results — could be drift OR genuinely empty",
            detail=detail,
        )

    first = listings[0]
    missing = _check_fields(first, search_required)
    if missing:
        return CheckResult(
            name=name,
            status="FAIL",
            summary=f"search result missing required fields: {missing}",
            detail=[*detail, f"first result keys: {sorted(first.keys())}"],
        )

    if details_from is None:
        return CheckResult(
            name=name,
            status="PASS",
            summary=f"search OK ({len(listings)} results, all required fields populated)",
            detail=detail,
        )

    try:
        d = details_from(first)
    except Exception as e:
        return CheckResult(
            name=name,
            status="FAIL",
            summary=f"details() raised {type(e).__name__}: {e}",
            detail=[*detail, traceback.format_exc()],
        )

    missing = _check_fields(d, details_required)
    if missing:
        return CheckResult(
            name=name,
            status="FAIL",
            summary=f"details missing required fields: {missing}",
            detail=[*detail, f"details keys: {sorted(d.keys())}"],
        )

    return CheckResult(
        name=name,
        status="PASS",
        summary=f"search + details OK ({len(listings)} results, all required fields populated)",
        detail=detail,
    )


# ---------- per-MCP smoke specs ----------


def _check_airbnb() -> CheckResult:
    from realestate_mcp.servers.airbnb import _client

    return _run(
        "airbnb",
        search=lambda: _client.search_stays(
            city="Asheville, NC",
            check_in=FUTURE_SAT_ISO,
            check_out=FUTURE_SAT_PLUS_7,
            adults=2,
            max_results=3,
        ),
        search_required=["listing_id", "name", "total_price"],
        details_from=lambda first: _client.get_listing_details(first["listing_id"]),
        details_required=["listing_id", "title"],
        results_key="listings",
    )


def _check_carolinadesigns() -> CheckResult:
    from realestate_mcp.servers.carolinadesigns import _client

    return _run(
        "carolinadesigns",
        search=lambda: _client.search_rentals(town="corolla", min_bedrooms=7, max_results=3),
        search_required=["listing_id", "name", "bedrooms", "bathrooms_full"],
        details_from=lambda first: _client.get_rental_details(first["listing_id"]),
        details_required=["listing_id", "name", "bedrooms"],
        results_key="listings",
    )


def _check_churchrealty() -> CheckResult:
    from realestate_mcp.servers.churchrealty import _client

    return _run(
        "churchrealty",
        search=lambda: _client.search_listings(state="TX", max_results=3),
        search_required=["listing_id", "name", "city", "state", "listing_type"],
        details_from=lambda first: _client.get_listing_details(first["listing_id"]),
        details_required=["listing_id", "name", "address", "price"],
        results_key="listings",
    )


def _check_crexi() -> CheckResult:
    from realestate_mcp.servers.crexi import _client

    return _run(
        "crexi",
        search=lambda: _client.search_properties(query="church", max_results=3),
        search_required=["listing_id", "name", "city", "state"],
        details_from=lambda first: _client.get_property_details(first["listing_id"]),
        details_required=["listing_id", "name"],
        results_key="properties",
    )


def _check_redfin() -> CheckResult:
    from realestate_mcp.servers.redfin import _client

    return _run(
        "redfin",
        search=lambda: _client.search_homes(zip_code="28704", max_results=3),
        search_required=["listing_id", "address", "city", "price"],
        # Redfin /home/<id> 404s — must use full URL
        details_from=lambda first: _client.get_home_details(first["url"]),
        details_required=["listing_id", "address", "price"],
        results_key="homes",
    )


def _check_sunrealty() -> CheckResult:
    from realestate_mcp.servers.sunrealty import _client

    return _run(
        "sunrealty",
        search=lambda: _client.search_rentals(town="duck", min_bedrooms=7, max_results=3),
        search_required=["listing_id", "name", "bedrooms"],
        details_from=lambda first: _client.get_rental_details(first["listing_id"]),
        details_required=["listing_id", "name"],
        results_key="listings",
    )


def _check_surforsound() -> CheckResult:
    from realestate_mcp.servers.surforsound import _client

    # No check_in date in the smoke — peak-week-availability filtering can drop
    # to 0 listings on popular dates and trigger a false WARN. Drift detection
    # only needs the basic search+detail path to work.
    return _run(
        "surforsound",
        search=lambda: _client.search_rentals(
            town="rodanthe", min_bedrooms=5, max_results=3
        ),
        search_required=["listing_id", "name", "bedrooms", "town"],
        details_from=lambda first: _client.get_rental_details(first["listing_id"]),
        details_required=["listing_id", "name", "bedrooms"],
        results_key="listings",
    )


def _check_twiddy() -> CheckResult:
    from realestate_mcp.servers.twiddy import _client

    return _run(
        "twiddy",
        search=lambda: _client.search_rentals(town="corolla", min_bedrooms=10, max_results=3),
        search_required=["listing_id", "name", "bedrooms"],
        details_from=lambda first: _client.get_rental_details(first["listing_id"]),
        details_required=["listing_id", "name", "bedrooms"],
        results_key="listings",
    )


CHECKS: list[Callable[[], CheckResult]] = [
    _check_airbnb,
    _check_carolinadesigns,
    _check_churchrealty,
    _check_crexi,
    _check_redfin,
    _check_sunrealty,
    _check_surforsound,
    _check_twiddy,
]


def main() -> int:
    print(f"Drift check — {date.today().isoformat()} (using future Sat={FUTURE_SAT_ISO})")
    print("=" * 80)
    results: list[CheckResult] = []
    for check in CHECKS:
        try:
            res = check()
        except Exception as e:
            res = CheckResult(
                name=check.__name__.removeprefix("_check_"),
                status="FAIL",
                summary=f"check itself raised {type(e).__name__}: {e}",
                detail=[traceback.format_exc()],
            )
        results.append(res)
        symbol = {"PASS": "+", "WARN": "?", "FAIL": "!"}[res.status]
        print(f"  [{symbol}] {res.status:4} {res.name:18}  {res.summary}")

    print("=" * 80)
    n_pass = sum(1 for r in results if r.status == "PASS")
    n_warn = sum(1 for r in results if r.status == "WARN")
    n_fail = sum(1 for r in results if r.status == "FAIL")
    print(f"Summary: {n_pass} PASS / {n_warn} WARN / {n_fail} FAIL  (out of {len(results)})")

    if n_fail or n_warn:
        print()
        print("Detail for non-PASS results:")
        for r in results:
            if r.status == "PASS":
                continue
            print(f"\n--- {r.name} ({r.status}) ---")
            for line in r.detail:
                print(line)

    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
