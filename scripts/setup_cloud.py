#!/usr/bin/env python3
"""One-shot cloud setup: push repo, set GitHub Actions secrets, run scraper."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRAPER_ENV = ROOT / "scraper" / ".env"
REPO = "MMprojekty/PokeDeals"
GITHUB_API = "https://api.github.com"


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


def save_env_value(path: Path, key: str, value: str) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
    line = f"{key}={value}"
    if pattern.search(text):
        text = pattern.sub(line, text)
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        text += line + "\n"
    path.write_text(text, encoding="utf-8")


def api_request(token: str, method: str, path: str, payload: dict | None = None) -> dict:
    url = f"{GITHUB_API}{path}"
    data = None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {method} {path} failed ({exc.code}): {body}") from exc


def ensure_pynacl():
    try:
        import nacl.public  # noqa: F401
        import nacl.encoding  # noqa: F401
        import nacl.utils  # noqa: F401
    except ImportError:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-q", "pynacl"],
            cwd=ROOT,
        )


def encrypt_secret(public_key_b64: str, secret_value: str) -> str:
    from nacl import encoding, public

    public_key = public.PublicKey(public_key_b64.encode("utf-8"), encoding.Base64Encoder())
    sealed_box = public.SealedBox(public_key)
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    return base64.b64encode(encrypted).decode("utf-8")


def set_repo_secret(token: str, name: str, value: str) -> None:
    key_info = api_request(token, "GET", f"/repos/{REPO}/actions/secrets/public-key")
    encrypted = encrypt_secret(key_info["key"], value)
    api_request(
        token,
        "PUT",
        f"/repos/{REPO}/actions/secrets/{name}",
        {"encrypted_value": encrypted, "key_id": key_info["key_id"]},
    )
    print(f"  secret set: {name}")


def git_push(token: str) -> None:
    remote = f"https://{token}@github.com/{REPO}.git"
    subprocess.run(["git", "remote", "set-url", "origin", remote], cwd=ROOT, check=True)
    result = subprocess.run(
        ["git", "push", "-u", "origin", "main"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        combined = f"{result.stdout}\n{result.stderr}"
        if "workflow" in combined.lower():
            raise RuntimeError(
                "GitHub blocked the push because your token is missing the workflow scope. "
                "Create a new classic token with BOTH repo and workflow checked, "
                "replace GITHUB_TOKEN in scraper/.env, then run setup again."
            )
        raise RuntimeError(f"git push failed:\n{combined}")
    subprocess.run(
        ["git", "remote", "set-url", "origin", f"https://github.com/{REPO}.git"],
        cwd=ROOT,
        check=True,
    )


def trigger_workflow(token: str) -> None:
    api_request(
        token,
        "POST",
        f"/repos/{REPO}/actions/workflows/scraper.yml/dispatches",
        {"ref": "main"},
    )
    print("  triggered workflow: Scrape shop prices")


def main() -> int:
    parser = argparse.ArgumentParser(description="Push PokeDeals to GitHub and configure cloud scraper.")
    parser.add_argument("--github-token", help="GitHub classic or fine-grained token with repo write access")
    parser.add_argument("--skip-push", action="store_true")
    parser.add_argument("--skip-secrets", action="store_true")
    parser.add_argument("--skip-run", action="store_true")
    parser.add_argument("--run-only", action="store_true", help="Only trigger the cloud scraper workflow.")
    parser.add_argument("--vercel", action="store_true", help="Also configure Vercel hosting after push.")
    parser.add_argument("--pages", action="store_true", help="Enable GitHub Pages hosting after push.")
    args = parser.parse_args()

    env = load_env(SCRAPER_ENV)
    token = (args.github_token or env.get("GITHUB_TOKEN", "")).strip()
    if not token:
        print("Missing GITHUB_TOKEN.")
        print("Add one line to scraper/.env:")
        print("  GITHUB_TOKEN=ghp_your_token_here")
        print("Then run: python3 scripts/setup_cloud.py")
        return 1

    if args.run_only:
        print("Triggering cloud scraper...")
        trigger_workflow(token)
        print(f"Done. Open https://github.com/{REPO}/actions to watch the run.")
        return 0

    if not args.github_token and not env.get("GITHUB_TOKEN"):
        save_env_value(SCRAPER_ENV, "GITHUB_TOKEN", token)

    required = ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "OPENAI_API_KEY"]
    missing = [key for key in required if not env.get(key)]
    if missing:
        print(f"Missing in scraper/.env: {', '.join(missing)}")
        return 1

    print("Checking GitHub access...")
    user = api_request(token, "GET", "/user")
    print(f"  signed in as: {user.get('login')}")

    try:
        repo = api_request(token, "GET", f"/repos/{REPO}")
        print(f"  repo found: {repo.get('full_name')}")
    except RuntimeError:
        print(f"  creating repo {REPO}...")
        api_request(token, "POST", "/user/repos", {"name": "PokeDeals", "private": True})

    if not args.skip_push:
        print("Pushing code to GitHub...")
        git_push(token)
        print("  push complete")

    if not args.skip_secrets:
        print("Setting GitHub Actions secrets...")
        ensure_pynacl()
        for key in required:
            set_repo_secret(token, key, env[key])

    if not args.skip_run:
        print("Starting cloud scraper...")
        trigger_workflow(token)
        print(f"Done. Open https://github.com/{REPO}/actions to watch the scraper.")

    if args.vercel:
        print("Configuring Vercel hosting...")
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "setup_vercel.py"), "--github-token", token],
            cwd=ROOT,
            check=False,
        )
        if result.returncode != 0:
            print("Vercel setup skipped — falling back to GitHub Pages.")
            args.pages = True

    if args.pages:
        print("Configuring GitHub Pages hosting...")
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "setup_pages.py"), "--github-token", token],
            cwd=ROOT,
            check=False,
        )
        if result.returncode != 0:
            return result.returncode

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
