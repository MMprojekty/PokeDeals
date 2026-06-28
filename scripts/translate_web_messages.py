#!/usr/bin/env python3
"""Generate web/messages/hu.json from en.json using OpenAI."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"
EN_FILE = WEB_DIR / "messages" / "en.json"
HU_FILE = WEB_DIR / "messages" / "hu.json"
SCRAPER_ENV = ROOT / "scraper" / ".env"

PLACEHOLDER_RE = re.compile(r"\{[a-zA-Z_]+\}")


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def flatten_messages(obj: Dict[str, Any], prefix: str = "") -> Dict[str, str]:
    flat: Dict[str, str] = {}
    for key, value in obj.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flat.update(flatten_messages(value, full_key))
        else:
            flat[full_key] = str(value)
    return flat


def unflatten_messages(flat: Dict[str, str]) -> Dict[str, Any]:
    root: Dict[str, Any] = {}
    for dotted_key, value in flat.items():
        parts = dotted_key.split(".")
        node = root
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
    return root


def validate_placeholders(source: Dict[str, str], translated: Dict[str, str]) -> list[str]:
    errors: list[str] = []
    for key, en_value in source.items():
        hu_value = translated.get(key, "")
        en_ph = PLACEHOLDER_RE.findall(en_value)
        hu_ph = PLACEHOLDER_RE.findall(hu_value)
        if sorted(en_ph) != sorted(hu_ph):
            errors.append(f"{key}: placeholders {en_ph} -> {hu_ph}")
    missing = set(source) - set(translated)
    if missing:
        errors.append(f"missing keys: {sorted(missing)}")
    return errors


def translate_with_openai(flat_en: Dict[str, str]) -> Dict[str, str]:
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY. Add it to scraper/.env")

    client = OpenAI(api_key=api_key)
    payload = json.dumps(flat_en, ensure_ascii=False, indent=2)
    prompt = f"""
You are a professional Hungarian UI translator for a Pokemon TCG price-comparison website (PokeDeals).

Translate EVERY value in this flat JSON from English to natural, fluent Hungarian.

Source JSON (keys stay English dotted paths; translate values only):
{payload}

Rules:
1) Return ONE JSON object with the EXACT same keys as the input.
2) Keep ICU placeholders unchanged and in the same positions: {{offers}}, {{products}}, {{prefix}}, {{age}}, {{inStock}}, {{total}}.
3) Keep brand name "PokéDeals" unchanged.
4) Use Hungarian that sounds native on a modern Hungarian e-commerce / collector site — not literal machine translation.
5) Use informal "te" form (e.g. "ellenőrizd", not "ellenőrizze").
6) "listings" means price listings/offers, NOT advertisements — never translate as "hirdetés".
7) "dashboard" = "főoldal", not "műszerfal".
8) Prefer terminology Hungarian TCG collectors actually use (booster doboz, bliszter, ETB, bundle are fine where common).
9) Keep "#" and "N/A" unchanged where appropriate.
10) Short UI labels should stay concise (buttons, table headers, filters).
11) Tooltips and longer sentences should be clear and natural Hungarian.
12) For sort aria-labels, use natural Hungarian like "Rendezés … szerint".
13) Do not add keys. Do not remove keys. JSON only, no markdown.
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    content = response.choices[0].message.content or "{}"
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise RuntimeError("OpenAI response was not a JSON object")
    return {str(k): str(v) for k, v in parsed.items()}


def load_message_files() -> tuple[Dict[str, Any], Dict[str, str], Dict[str, str]]:
    if not EN_FILE.exists():
        raise FileNotFoundError(f"Missing {EN_FILE}")
    en_nested = json.loads(EN_FILE.read_text(encoding="utf-8"))
    flat_en = flatten_messages(en_nested)
    flat_hu: Dict[str, str] = {}
    if HU_FILE.exists():
        hu_nested = json.loads(HU_FILE.read_text(encoding="utf-8"))
        flat_hu = flatten_messages(hu_nested)
    return en_nested, flat_en, flat_hu


def translation_is_stale(flat_en: Dict[str, str], flat_hu: Dict[str, str]) -> bool:
    if not HU_FILE.exists():
        return True
    if set(flat_en) != set(flat_hu):
        return True
    if EN_FILE.stat().st_mtime > HU_FILE.stat().st_mtime:
        return True
    return False


def write_hu_file(flat_en: Dict[str, str], flat_hu: Dict[str, str]) -> None:
    errors = validate_placeholders(flat_en, flat_hu)
    if errors:
        print("Validation failed:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        raise RuntimeError("Hungarian translation validation failed")

    hu_nested = unflatten_messages(flat_hu)
    HU_FILE.write_text(json.dumps(hu_nested, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {HU_FILE}")


def run_translation(flat_en: Dict[str, str]) -> Dict[str, str]:
    print(f"Translating {len(flat_en)} UI strings to Hungarian…")
    return translate_with_openai(flat_en)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Hungarian UI messages with OpenAI.")
    parser.add_argument(
        "--if-stale",
        action="store_true",
        help="Only translate when en.json changed or hu.json is missing/out of date.",
    )
    args = parser.parse_args()

    load_dotenv(SCRAPER_ENV)
    web_env = WEB_DIR / ".env.local"
    load_dotenv(web_env)

    try:
        _, flat_en, flat_hu = load_message_files()
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.if_stale and not translation_is_stale(flat_en, flat_hu):
        return 0

    if not os.getenv("OPENAI_API_KEY", "").strip():
        if args.if_stale:
            print("Skipping Hungarian auto-translation: OPENAI_API_KEY not set.", file=sys.stderr)
            return 0
        print("Missing OPENAI_API_KEY. Add it to scraper/.env", file=sys.stderr)
        return 1

    try:
        flat_hu = run_translation(flat_en)
        write_hu_file(flat_en, flat_hu)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
