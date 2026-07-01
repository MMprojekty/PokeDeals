#!/usr/bin/env python3
"""Verify external scrape trigger and print cron-job.org setup (Option A)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRAPER_ENV = ROOT / "scraper" / ".env"
REPO = os.environ.get("GITHUB_REPO", "MMprojekty/PokeDeals")
WORKFLOW_FILE = "scraper.yml"
GITHUB_API = "https://api.github.com"
VERCEL_SITE = os.environ.get("NEXT_PUBLIC_SITE_URL", "https://pokedeals-liart.vercel.app").rstrip("/")


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def github_request(token: str, method: str, path: str, payload: dict | None = None) -> tuple[int, str]:
    url = f"{GITHUB_API}{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def test_github_dispatch(token: str, dry_run: bool) -> bool:
    owner, name = REPO.split("/", 1)
    path = f"/repos/{owner}/{name}/actions/workflows/{WORKFLOW_FILE}/dispatches"
    payload = {"ref": "main", "inputs": {"force": "true"}}
    if dry_run:
        print("  dry-run: would POST GitHub workflow dispatch")
        return True
    status, body = github_request(token, "POST", path, payload)
    if status == 204:
        print("  GitHub dispatch OK (204) — scraper workflow started.")
        return True
    print(f"  GitHub dispatch failed: HTTP {status}")
    if body:
        print(f"  {body[:500]}")
    return False


def test_vercel_cron(secret: str, dry_run: bool) -> bool:
    url = f"{VERCEL_SITE}/api/cron/scrape"
    if dry_run:
        print(f"  dry-run: would GET {url}")
        return True
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {secret}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            print(f"  Vercel cron endpoint OK ({response.status}): {body[:200]}")
            return 200 <= response.status < 300
    except urllib.error.HTTPError as exc:
        print(f"  Vercel cron endpoint failed: HTTP {exc.code}")
        print(exc.read().decode("utf-8")[:500])
        return False


def print_github_cron_job_instructions(token_hint: str) -> None:
    owner, name = REPO.split("/", 1)
    url = f"{GITHUB_API}/repos/{owner}/{name}/actions/workflows/{WORKFLOW_FILE}/dispatches"
    print(
        f"""
================================================================================
OPTION A — cron-job.org → GitHub (recommended token: dedicated fine-grained PAT)
================================================================================

1. Create a fine-grained PAT (if you don't want to reuse your main token):
   https://github.com/settings/personal-access-tokens/new
   - Repository access: Only "{name}"
   - Permissions: Actions = Read and write, Metadata = Read
   - Name it: cron-job-scrape-trigger

2. Sign up / log in: https://console.cron-job.org/

3. Create cronjob → "Create cronjob":
   - Title: PokeDeals scraper
   - URL: {url}
   - Schedule: Every 30 minutes  (or custom: */30 * * * *)
   - Request method: POST
   - Request body (raw JSON):
       {{"ref":"main","inputs":{{"force":"true"}}}}

4. Request headers (add each):
   - Authorization: Bearer <YOUR_PAT>
   - Accept: application/vnd.github+json
   - X-GitHub-Api-Version: 2022-11-28
   - Content-Type: application/json

5. Enable the job and save.

Token in use for this test: {token_hint}

Verify: GitHub → Actions → "Scrape shop prices" should run every ~30 min.
================================================================================
"""
    )


def print_vercel_cron_job_instructions(site_url: str) -> None:
    url = f"{site_url}/api/cron/scrape"
    print(
        f"""
================================================================================
OPTION A (simpler) — cron-job.org → your Vercel site
================================================================================

Uses CRON_SECRET from Vercel (set by scripts/setup_vercel.py).
No GitHub PAT needed in cron-job.org.

1. Get CRON_SECRET from: Vercel → pokedeals → Settings → Environment Variables

2. https://console.cron-job.org/ → Create cronjob:
   - Title: PokeDeals scraper
   - URL: {url}
   - Schedule: Every 30 minutes
   - Request method: GET
   - Header: Authorization = Bearer <CRON_SECRET>

3. Save and enable.

The site will trigger GitHub only when data is stale (saves scraper runs).
For always scrape every 30 min, use the GitHub API method instead.
================================================================================
"""
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Set up cron-job.org external scrape trigger.")
    parser.add_argument("--token", help="GitHub PAT with actions:write on the repo")
    parser.add_argument(
        "--mode",
        choices=("github", "vercel", "both"),
        default="github",
        help="github = dispatch GitHub Actions directly (default). vercel = hit /api/cron/scrape.",
    )
    parser.add_argument("--cron-secret", help="CRON_SECRET for vercel mode (or read from env)")
    parser.add_argument("--dry-run", action="store_true", help="Print instructions only, do not trigger")
    args = parser.parse_args()

    env = load_env(SCRAPER_ENV)
    ok = True

    if args.mode in ("github", "both"):
        token = (args.token or env.get("GITHUB_TOKEN", "")).strip()
        if not token:
            print("Missing GitHub token. Pass --token or set GITHUB_TOKEN in scraper/.env")
            return 1
        hint = f"{token[:7]}…{token[-4:]}" if len(token) > 12 else "(short token)"
        print("Testing GitHub workflow dispatch…")
        ok = test_github_dispatch(token, args.dry_run) and ok
        print_github_cron_job_instructions(hint)

    if args.mode in ("vercel", "both"):
        secret = (args.cron_secret or env.get("CRON_SECRET", "")).strip()
        if not secret:
            print(
                "\nNo CRON_SECRET found. Run scripts/setup_vercel.py or pass --cron-secret.\n"
                "Skipping Vercel endpoint test."
            )
        else:
            print(f"\nTesting Vercel cron endpoint ({VERCEL_SITE})…")
            ok = test_vercel_cron(secret, args.dry_run) and ok
        print_vercel_cron_job_instructions(VERCEL_SITE)

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
