#!/usr/bin/env python3
"""Backfill new_since_update.json from the last two snapshots that have product_keys."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scraper"))

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv:
    load_dotenv(dotenv_path=ROOT / "scraper" / ".env")

from supabase import create_client

STATS_BUCKET = "pokedeals-meta"
STATS_OBJECT = "stats_snapshots.json"
NEW_SINCE_UPDATE_OBJECT = "new_since_update.json"


def _token_overlap(a: str, b: str) -> float:
    ta = set(a.split())
    tb = set(b.split())
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    return inter / len(ta | tb)


def _filter_renamed_keys(candidate_keys: list[str], previous_keys: set[str]) -> list[str]:
    if not previous_keys:
        return candidate_keys
    kept: list[str] = []
    previous = list(previous_keys)
    for key in candidate_keys:
        if key in previous_keys:
            continue
        if any(_token_overlap(key, prev) >= 0.65 for prev in previous):
            continue
        kept.append(key)
    return sorted(kept)


def main() -> int:
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        print("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in scraper/.env")
        return 1

    supabase = create_client(url, key)
    raw = supabase.storage.from_(STATS_BUCKET).download(STATS_OBJECT)
    payload = json.loads(raw.decode("utf-8"))
    snapshots = payload.get("snapshots") or []
    if len(snapshots) < 2:
        print("Need at least two stats snapshots.")
        return 1

    newer = snapshots[-1]
    older = snapshots[-2]
    newer_keys = newer.get("product_keys") or []
    older_keys = older.get("product_keys") or []
    if not newer_keys:
        print("Latest snapshot has no product_keys yet — wait for the next scraper run.")
        return 1
    if not older_keys:
        print("Previous snapshot has no product_keys — the next scraper run will record new products.")
        return 1

    new_product_keys = sorted(set(newer_keys) - set(older_keys))
    new_product_keys = _filter_renamed_keys(new_product_keys, set(older_keys))
    newer_offers = set(newer.get("offer_keys") or [])
    older_offers = set(older.get("offer_keys") or [])
    new_offer_keys = sorted(newer_offers - older_offers)
    new_offer_product_keys = sorted(
        {key.split("|", 1)[1] for key in new_offer_keys if "|" in key}
    )

    body = json.dumps(
        {
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "product_keys": new_product_keys,
            "offer_product_keys": new_offer_product_keys,
        }
    ).encode("utf-8")
    supabase.storage.from_(STATS_BUCKET).upload(
        NEW_SINCE_UPDATE_OBJECT,
        body,
        file_options={"content-type": "application/json", "upsert": "true"},
    )
    print(
        f"Backfilled {NEW_SINCE_UPDATE_OBJECT}: "
        f"{len(new_product_keys)} new products, {len(new_offer_product_keys)} products with new offers."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
