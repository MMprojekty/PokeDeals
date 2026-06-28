#!/usr/bin/env python3
"""Refresh AI market trend rankings for products currently in shop_listings."""

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

from market_trends import refresh_market_trends  # noqa: E402
from scraper import LISTINGS_TABLE, get_clients  # noqa: E402


def main() -> None:
    supabase, ai = get_clients(use_ai_matching=True)
    if not ai:
        print("OPENAI_API_KEY is required.")
        raise SystemExit(1)

    response = supabase.table(LISTINGS_TABLE).select("raw_title, stock_status").execute()
    rows = response.data or []
    titles = [
        str(row.get("raw_title", "")).strip()
        for row in rows
        if "IN_STOCK" in str(row.get("stock_status", "")).upper()
    ]
    if not titles:
        print("No in-stock titles found.")
        return

    payload = refresh_market_trends(supabase, ai, titles, force=True)
    ranked = payload.get("ranked", [])
    print(f"Updated market trends ({len(ranked)} products).")
    note = payload.get("market_note")
    if note:
        print(f"Market note: {note}")


if __name__ == "__main__":
    main()
