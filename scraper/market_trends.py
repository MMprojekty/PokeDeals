"""OpenAI-powered Pokemon TCG market demand ranking for in-catalog products."""

from __future__ import annotations

import json
import logging
import os
import re
import time
import unicodedata
from datetime import datetime, timezone
from typing import Dict, List, Optional

from openai import OpenAI
from supabase import Client

logger = logging.getLogger("pokedeals-scraper")

STATS_BUCKET = "pokedeals-meta"
MARKET_TRENDS_OBJECT = "market_trends.json"
TRENDS_MAX_AGE_SECONDS = int(os.getenv("TRENDS_MAX_AGE_SECONDS", str(6 * 3600)))
MAX_CATALOG_TITLES = 80


def canonical_key_for_grouping(name: str) -> str:
    text = unicodedata.normalize("NFD", name)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.lower()
    text = re.sub(r"pokemon\s*tcg[:\-\s]*", " ", text)
    text = re.sub(r"pokemon[:\-\s]*", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _ensure_meta_bucket(supabase_client: Client) -> None:
    try:
        supabase_client.storage.get_bucket(STATS_BUCKET)
    except Exception:
        try:
            supabase_client.storage.create_bucket(STATS_BUCKET, options={"public": False})
        except Exception:
            pass


def load_cached_trends(supabase_client: Client) -> Optional[Dict[str, object]]:
    _ensure_meta_bucket(supabase_client)
    try:
        raw = supabase_client.storage.from_(STATS_BUCKET).download(MARKET_TRENDS_OBJECT)
        payload = json.loads(raw.decode("utf-8"))
        if isinstance(payload, dict) and isinstance(payload.get("ranked"), list):
            return payload
    except Exception:
        return None
    return None


def save_trends(supabase_client: Client, payload: Dict[str, object]) -> None:
    last_exc: Optional[Exception] = None
    for attempt in range(1, 4):
        try:
            _ensure_meta_bucket(supabase_client)
            body = json.dumps(payload).encode("utf-8")
            supabase_client.storage.from_(STATS_BUCKET).upload(
                MARKET_TRENDS_OBJECT,
                body,
                file_options={"content-type": "application/json", "upsert": "true"},
            )
            return
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < 3:
                time.sleep(2 * attempt)
    if last_exc:
        raise last_exc


def _cache_is_fresh(payload: Dict[str, object]) -> bool:
    updated_at = str(payload.get("updated_at") or "")
    if not updated_at:
        return False
    try:
        parsed = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    age = (datetime.now(timezone.utc) - parsed).total_seconds()
    return age < TRENDS_MAX_AGE_SECONDS


def fetch_trends_from_openai(ai_client: OpenAI, catalog_titles: List[str]) -> Dict[str, object]:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    titles = catalog_titles[:MAX_CATALOG_TITLES]
    prompt = f"""
You are a Pokemon TCG market analyst for collectors in Hungary and wider Europe.
Today is {today}.

We operate a price comparison site for sealed English Pokemon TCG products currently in stock at Hungarian webshops.

Catalog titles to rank (ONLY use names from this list):
{json.dumps(titles, ensure_ascii=False)}

Task:
1) Identify which catalog products are most demanded, searched for, or newly relevant in the current Pokemon TCG market.
2) Consider: recent or upcoming set releases, pre-order hype, tournament relevance, collector demand, booster box / ETB interest, and general community buzz.
3) Rank up to 30 products from the catalog by current market demand (highest first).
4) Assign each a demand_score from 0-100 (100 = extremely hot right now).

Return JSON only:
{{
  "ranked": [
    {{
      "canonical_title": "exact or closest catalog title",
      "demand_score": 0,
      "signal": "new_release|high_demand|collector_favorite|competitive|restock_interest|steady"
    }}
  ],
  "market_note": "one short sentence about current HU/EU Pokemon TCG demand"
}}
"""
    response = ai_client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    parsed = json.loads(response.choices[0].message.content)
    ranked = parsed.get("ranked") if isinstance(parsed, dict) else []
    if not isinstance(ranked, list):
        ranked = []

    cleaned: List[Dict[str, object]] = []
    catalog_keys = {canonical_key_for_grouping(title): title for title in titles}
    for entry in ranked:
        if not isinstance(entry, dict):
            continue
        title = str(entry.get("canonical_title") or "").strip()
        if not title:
            continue
        key = canonical_key_for_grouping(title)
        if key not in catalog_keys:
            title_tokens = set(key.split())
            match_key = None
            for catalog_key in catalog_keys:
                catalog_tokens = set(catalog_key.split())
                if title_tokens and title_tokens & catalog_tokens:
                    overlap = len(title_tokens & catalog_tokens) / max(len(title_tokens), 1)
                    if overlap >= 0.6:
                        match_key = catalog_key
                        break
            if not match_key:
                continue
            title = catalog_keys[match_key]
            key = match_key

        try:
            score = int(entry.get("demand_score", 50))
        except (TypeError, ValueError):
            score = 50
        score = max(0, min(score, 100))
        cleaned.append(
            {
                "canonical_title": title,
                "demand_score": score,
                "signal": str(entry.get("signal") or "steady"),
            }
        )

    return {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ranked": cleaned[:30],
        "market_note": str(parsed.get("market_note") or "").strip(),
        "catalog_size": len(titles),
    }


def refresh_market_trends(
    supabase_client: Client,
    ai_client: OpenAI,
    catalog_titles: List[str],
    force: bool = False,
) -> Dict[str, object]:
    unique_titles = sorted({title.strip() for title in catalog_titles if title and title.strip()})
    if not unique_titles:
        return {"updated_at": None, "ranked": [], "market_note": ""}

    if not force:
        cached = load_cached_trends(supabase_client)
        if cached and _cache_is_fresh(cached):
            logger.info("Using cached market trends (%d ranked products).", len(cached.get("ranked", [])))
            return cached

    logger.info("Fetching market trends from OpenAI for %d catalog products...", len(unique_titles))
    payload = fetch_trends_from_openai(ai_client, unique_titles)
    save_trends(supabase_client, payload)
    logger.info("Saved market trends: %d ranked products.", len(payload.get("ranked", [])))
    return payload


def trend_score_map(payload: Optional[Dict[str, object]]) -> Dict[str, int]:
    if not payload:
        return {}
    ranked = payload.get("ranked")
    if not isinstance(ranked, list):
        return {}
    result: Dict[str, int] = {}
    for entry in ranked:
        if not isinstance(entry, dict):
            continue
        title = str(entry.get("canonical_title") or "").strip()
        if not title:
            continue
        try:
            score = int(entry.get("demand_score", 50))
        except (TypeError, ValueError):
            score = 50
        result[canonical_key_for_grouping(title)] = max(0, min(score, 100))
    return result
