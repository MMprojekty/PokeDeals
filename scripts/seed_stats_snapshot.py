#!/usr/bin/env python3
"""Insert a baseline stats snapshot from current shop_listings (run once to enable deltas)."""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scraper"))

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv:
    load_dotenv(os.path.join(ROOT, "scraper", ".env"))

from scraper import (  # noqa: E402
    LISTINGS_TABLE,
    STATS_BUCKET,
    compute_run_stats,
    get_clients,
    store_stats_snapshot,
)


def main() -> None:
    supabase, _ = get_clients(use_ai_matching=False)
    response = supabase.table(LISTINGS_TABLE).select("shop_name, raw_title, stock_status").execute()
    rows = response.data or []
    in_stock = [
        row
        for row in rows
        if "IN_STOCK" in str(row.get("stock_status", "")).upper()
    ]
    if not in_stock:
        print("No in-stock listings found; nothing to seed.")
        return

    stats = compute_run_stats(in_stock)
    store_stats_snapshot(supabase, stats)
    print(
        f"Seeded {STATS_BUCKET}/stats_snapshots.json: "
        f"{stats['in_stock_products']} products, "
        f"{stats['shops_count']} shops, "
        f"{stats['in_stock_offers']} offers."
    )


if __name__ == "__main__":
    main()
