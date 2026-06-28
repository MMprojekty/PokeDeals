#!/usr/bin/env python3
"""Exit with stale=true when shop_listings data is older than the hourly target."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

STALE_AFTER_MINUTES = int(os.environ.get("SCRAPE_STALE_MINUTES", "65"))


def main() -> int:
    supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    table = os.environ.get("SUPABASE_LISTINGS_TABLE", "shop_listings")

    if not supabase_url or not service_key:
        print("error=missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY", file=sys.stderr)
        return 1

    request = urllib.request.Request(
        f"{supabase_url}/rest/v1/{table}?select=updated_at&order=updated_at.desc&limit=1",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            rows = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        print(f"error={exc}", file=sys.stderr)
        return 1

    if not rows:
        age_minutes = 9999
    else:
        latest = str(rows[0].get("updated_at") or "")
        parsed = datetime.fromisoformat(latest.replace("Z", "+00:00"))
        age_minutes = int((datetime.now(timezone.utc) - parsed).total_seconds() // 60)

    stale = age_minutes > STALE_AFTER_MINUTES
    print(f"age_minutes={age_minutes}")
    print(f"stale={'true' if stale else 'false'}")

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as handle:
            handle.write(f"stale={'true' if stale else 'false'}\n")
            handle.write(f"age_minutes={age_minutes}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
