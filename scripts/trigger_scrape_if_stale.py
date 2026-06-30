#!/usr/bin/env python3
"""Trigger the scraper workflow when data is stale and no scrape is already running."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

REPO = os.environ.get("GITHUB_REPO", "MMprojekty/PokeDeals")
STALE_AFTER_MINUTES = int(os.environ.get("SCRAPE_STALE_MINUTES", "35"))
WORKFLOW_FILE = "scraper.yml"


def github_request(token: str, method: str, path: str, payload: dict | None = None) -> object:
    url = f"https://api.github.com{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read().decode("utf-8")
        return json.loads(body) if body else {}


def latest_data_age_minutes() -> int:
    supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    table = os.environ.get("SUPABASE_LISTINGS_TABLE", "shop_listings")
    if not supabase_url or not service_key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")

    request = urllib.request.Request(
        f"{supabase_url}/rest/v1/{table}?select=updated_at&order=updated_at.desc&limit=1",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        rows = json.loads(response.read().decode("utf-8"))
    if not rows:
        return 9999

    latest = str(rows[0].get("updated_at") or "")
    parsed = datetime.fromisoformat(latest.replace("Z", "+00:00"))
    return int((datetime.now(timezone.utc) - parsed).total_seconds() // 60)


def scrape_in_progress(token: str) -> bool:
    owner, repo = REPO.split("/", 1)
    payload = github_request(
        token,
        "GET",
        f"/repos/{owner}/{repo}/actions/workflows/{WORKFLOW_FILE}/runs?status=in_progress&per_page=5",
    )
    runs = payload.get("workflow_runs") or []
    return len(runs) > 0


def dispatch_force_scrape(token: str) -> None:
    owner, repo = REPO.split("/", 1)
    github_request(
        token,
        "POST",
        f"/repos/{owner}/{repo}/actions/workflows/{WORKFLOW_FILE}/dispatches",
        {"ref": "main", "inputs": {"force": "true"}},
    )


def main() -> int:
    github_token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not github_token:
        print("error=missing GITHUB_TOKEN", file=sys.stderr)
        return 1

    try:
        age_minutes = latest_data_age_minutes()
    except (urllib.error.URLError, RuntimeError, ValueError) as exc:
        print(f"error={exc}", file=sys.stderr)
        return 1

    stale = age_minutes > STALE_AFTER_MINUTES
    print(f"age_minutes={age_minutes}")
    print(f"stale={'true' if stale else 'false'}")

    if not stale:
        print("action=skip_fresh")
        return 0

    try:
        if scrape_in_progress(github_token):
            print("action=skip_in_progress")
            return 0
    except urllib.error.URLError as exc:
        print(f"warning=in_progress_check_failed detail={exc}", file=sys.stderr)

    try:
        dispatch_force_scrape(github_token)
    except urllib.error.URLError as exc:
        print(f"error=dispatch_failed detail={exc}", file=sys.stderr)
        return 1

    print("action=triggered")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
