#!/usr/bin/env python3
"""Create/configure a Vercel project and store deploy secrets in GitHub."""

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
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRAPER_ENV = ROOT / "scraper" / ".env"
REPO = "MMprojekty/PokeDeals"
PROJECT_NAME = "pokedeals"
VERCEL_API = "https://api.vercel.com"
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


def vercel_request(token: str, method: str, path: str, payload: dict | None = None, params: str = "") -> Any:
    url = f"{VERCEL_API}{path}"
    if params:
        url = f"{url}?{params}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Vercel API {method} {path} failed ({exc.code}): {body}") from exc


def github_request(token: str, method: str, path: str, payload: dict | None = None) -> Any:
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


def ensure_pynacl() -> None:
    try:
        import nacl.public  # noqa: F401
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "pynacl"], cwd=ROOT)


def set_github_secret(github_token: str, name: str, value: str) -> None:
    from nacl import encoding, public

    key_info = github_request(github_token, "GET", f"/repos/{REPO}/actions/secrets/public-key")
    public_key = public.PublicKey(key_info["key"].encode("utf-8"), encoding.Base64Encoder())
    sealed_box = public.SealedBox(public_key)
    encrypted = base64.b64encode(sealed_box.encrypt(value.encode("utf-8"))).decode("utf-8")
    github_request(
        github_token,
        "PUT",
        f"/repos/{REPO}/actions/secrets/{name}",
        {"encrypted_value": encrypted, "key_id": key_info["key_id"]},
    )
    print(f"  github secret set: {name}")


def read_vercel_auth_files() -> str:
    candidates = [
        Path.home() / ".local/share/com.vercel.cli/auth.json",
        Path.home() / "Library/Application Support/com.vercel.cli/auth.json",
        Path.home() / ".config/com.vercel.cli/auth.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        token = str(data.get("token") or "").strip()
        if token:
            print(f"  found Vercel token in {path}")
            return token
    return ""


def read_vercel_token_from_keychain() -> str:
    if sys.platform != "darwin":
        return ""
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", "vercel", "-w"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    token = (result.stdout or "").strip()
    return token if result.returncode == 0 and token else ""


def resolve_vercel_token(env: dict[str, str], github_token: str) -> str:
    token = env.get("VERCEL_TOKEN", "").strip()
    if token:
        return token
    token = read_vercel_auth_files()
    if token:
        return token
    token = read_vercel_token_from_keychain()
    if token:
        print("  found Vercel token in macOS keychain")
        return token
    token = try_bootstrap_vercel_with_github(github_token)
    if token:
        print("  created Vercel access token via GitHub")
        return token
    raise RuntimeError(
        "No Vercel access token found. Add VERCEL_TOKEN to scraper/.env — create one at "
        "https://vercel.com/account/settings/tokens (free Hobby plan is fine)."
    )


def try_bootstrap_vercel_with_github(github_token: str) -> str:
    """Best-effort: reuse GitHub identity if Vercel already linked the same account."""
    try:
        vercel_request(github_token, "GET", "/v2/user")
        return github_token
    except RuntimeError:
        return ""


def find_project(vercel_token: str, team_id: str | None) -> dict | None:
    query = f"teamId={team_id}" if team_id else ""
    projects = vercel_request(vercel_token, "GET", "/v9/projects", params=query)
    for project in projects.get("projects", []):
        if project.get("name") == PROJECT_NAME:
            return project
    return None


def create_or_update_project(vercel_token: str, team_id: str | None) -> dict:
    existing = find_project(vercel_token, team_id)
    body = {
        "name": PROJECT_NAME,
        "framework": "nextjs",
        "rootDirectory": "web",
        "gitRepository": {
            "type": "github",
            "repo": REPO,
        },
        "buildCommand": "npm run build",
        "installCommand": "npm install",
    }
    if existing:
        project_id = existing["id"]
        query = f"teamId={team_id}" if team_id else ""
        print(f"  updating Vercel project: {PROJECT_NAME}")
        return vercel_request(vercel_token, "PATCH", f"/v9/projects/{project_id}", body, params=query)

    query = f"teamId={team_id}" if team_id else ""
    print(f"  creating Vercel project: {PROJECT_NAME}")
    return vercel_request(vercel_token, "POST", "/v11/projects", body, params=query)


def set_project_env(
    vercel_token: str,
    project_id: str,
    team_id: str | None,
    key: str,
    value: str,
    target: list[str] | None = None,
) -> None:
    query = f"teamId={team_id}" if team_id else ""
    payload = {
        "key": key,
        "value": value,
        "type": "encrypted",
        "target": target or ["production", "preview", "development"],
    }
    vercel_request(vercel_token, "POST", f"/v10/projects/{project_id}/env", payload, params=query)


def upsert_env_vars(
    vercel_token: str,
    project_id: str,
    team_id: str | None,
    values: dict[str, str],
) -> None:
    query = f"teamId={team_id}" if team_id else ""
    existing = vercel_request(vercel_token, "GET", f"/v9/projects/{project_id}/env", params=query)
    by_key = {item.get("key"): item for item in existing.get("envs", [])}
    for key, value in values.items():
        if not value:
            continue
        current = by_key.get(key)
        if current:
            env_id = current["id"]
            vercel_request(
                vercel_token,
                "PATCH",
                f"/v9/projects/{project_id}/env/{env_id}",
                {"value": value, "target": ["production", "preview", "development"]},
                params=query,
            )
            print(f"  env updated: {key}")
        else:
            set_project_env(vercel_token, project_id, team_id, key, value)
            print(f"  env set: {key}")


def trigger_deploy(vercel_token: str, team_id: str | None, project_name: str) -> dict:
    payload = {
        "name": project_name,
        "target": "production",
        "gitSource": {
            "type": "github",
            "org": REPO.split("/")[0],
            "repo": REPO.split("/")[1],
            "ref": "main",
        },
    }
    query = f"teamId={team_id}" if team_id else ""
    print("  triggering production deployment...")
    return vercel_request(vercel_token, "POST", "/v13/deployments", payload, params=query)


def deployment_url(deployment: dict) -> str:
    url = deployment.get("url") or ""
    if url and not url.startswith("http"):
        return f"https://{url}"
    return url


def main() -> int:
    parser = argparse.ArgumentParser(description="Configure Vercel hosting for PokeDeals web app.")
    parser.add_argument("--github-token", help="GitHub token with repo admin (for storing secrets)")
    parser.add_argument("--skip-github-secrets", action="store_true")
    args = parser.parse_args()

    env = load_env(SCRAPER_ENV)
    github_token = (args.github_token or env.get("GITHUB_TOKEN", "")).strip()
    if not github_token and not args.skip_github_secrets:
        print("Missing GITHUB_TOKEN in scraper/.env")
        return 1

    try:
        vercel_token = resolve_vercel_token(env, github_token)
    except RuntimeError as exc:
        print(str(exc))
        return 1

    if not env.get("VERCEL_TOKEN"):
        save_env_value(SCRAPER_ENV, "VERCEL_TOKEN", vercel_token)

    user = vercel_request(vercel_token, "GET", "/v2/user")
    print(f"  Vercel user: {user.get('user', {}).get('username') or user.get('username')}")

    team_id = None  # Hobby accounts use personal scope (no teamId).

    project = create_or_update_project(vercel_token, team_id)
    project_id = project["id"]
    org_id = project.get("accountId") or user.get("user", {}).get("id") or user.get("id")

    site_url = f"https://{PROJECT_NAME}.vercel.app"
    env_values = {
        "SUPABASE_URL": env.get("SUPABASE_URL", ""),
        "SUPABASE_SERVICE_ROLE_KEY": env.get("SUPABASE_SERVICE_ROLE_KEY", ""),
        "SUPABASE_LISTINGS_TABLE": env.get("SUPABASE_LISTINGS_TABLE", "shop_listings"),
        "NEXT_PUBLIC_SITE_URL": site_url,
    }
    print("Setting Vercel environment variables...")
    upsert_env_vars(vercel_token, project_id, team_id, env_values)

    if not args.skip_github_secrets:
        print("Storing Vercel deploy secrets in GitHub...")
        ensure_pynacl()
        set_github_secret(github_token, "VERCEL_TOKEN", vercel_token)
        set_github_secret(github_token, "VERCEL_ORG_ID", str(org_id))
        set_github_secret(github_token, "VERCEL_PROJECT_ID", str(project_id))

    try:
        deployment = trigger_deploy(vercel_token, team_id, PROJECT_NAME)
        url = deployment_url(deployment)
        print(f"  deployment started: {url or deployment.get('id')}")
        if url:
            print(f"\nLive site (building): {url}")
    except RuntimeError as exc:
        print(f"  deploy trigger skipped: {exc}")
        print(f"  Git pushes to main will deploy via Vercel Git integration or deploy-web.yml")

    print(f"\nProject dashboard: https://vercel.com/{user.get('user', {}).get('username', '')}/{PROJECT_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
