#!/usr/bin/env python3
"""Enable GitHub Pages (workflow build) and trigger the first deploy."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = "MMprojekty/PokeDeals"
GITHUB_API = "https://api.github.com"
SCRAPER_ENV = Path(__file__).resolve().parents[1] / "scraper" / ".env"
PAGES_URL = "https://mmprojekty.github.io/PokeDeals"


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


def github_request(token: str, method: str, path: str, payload: dict | None = None) -> dict:
    url = f"{GITHUB_API}{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    if payload is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {method} {path} failed ({exc.code}): {body}") from exc


def enable_pages(token: str) -> None:
    try:
        github_request(
            token,
            "POST",
            f"/repos/{REPO}/pages",
            {"build_type": "workflow"},
        )
        print("  enabled GitHub Pages (workflow build)")
    except RuntimeError as exc:
        message = str(exc)
        if "does not support GitHub Pages" in message:
            print("  free GitHub Pages needs a public repository — making repo public...")
            github_request(token, "PATCH", f"/repos/{REPO}", {"private": False})
            github_request(
                token,
                "POST",
                f"/repos/{REPO}/pages",
                {"build_type": "workflow"},
            )
            print("  enabled GitHub Pages (workflow build)")
            return
        if "409" in message or "422" in message:
            try:
                github_request(
                    token,
                    "PUT",
                    f"/repos/{REPO}/pages",
                    {"build_type": "workflow"},
                )
                print("  updated GitHub Pages to workflow build")
                return
            except RuntimeError as put_exc:
                if "404" in str(put_exc):
                    github_request(
                        token,
                        "POST",
                        f"/repos/{REPO}/pages",
                        {"build_type": "workflow"},
                    )
                    print("  enabled GitHub Pages (workflow build)")
                    return
                raise
        raise


def trigger_pages_deploy(token: str) -> None:
    github_request(
        token,
        "POST",
        f"/repos/{REPO}/actions/workflows/deploy-pages.yml/dispatches",
        {"ref": "main"},
    )
    print("  triggered workflow: Deploy web (GitHub Pages)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Enable GitHub Pages hosting for PokeDeals.")
    parser.add_argument("--github-token")
    args = parser.parse_args()

    env = load_env(SCRAPER_ENV)
    token = (args.github_token or env.get("GITHUB_TOKEN", "")).strip()
    if not token:
        print("Missing GITHUB_TOKEN in scraper/.env")
        return 1

    print("Configuring GitHub Pages...")
    enable_pages(token)
    trigger_pages_deploy(token)
    print(f"\nSite will be live at: {PAGES_URL}")
    print(f"Track build: https://github.com/{REPO}/actions/workflows/deploy-pages.yml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
