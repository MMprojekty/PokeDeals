import json
import logging
import os
from datetime import date
from pathlib import Path
from typing import Dict, Optional, Tuple

import requests

logger = logging.getLogger("pokedeals-scraper")

CACHE_FILE = Path(__file__).with_name(".eur_huf_rate.json")
FRANKFURTER_URL = "https://api.frankfurter.app/latest?from=EUR&to=HUF"
FALLBACK_RATE = float(os.getenv("EUR_TO_HUF_RATE", "395"))


def _read_cache() -> Optional[Dict[str, object]]:
    if not CACHE_FILE.exists():
        return None
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read exchange-rate cache: %s", exc)
        return None


def _write_cache(rate: float, rate_date: str) -> None:
    payload = {"date": rate_date, "rate": rate}
    try:
        CACHE_FILE.write_text(json.dumps(payload), encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not write exchange-rate cache: %s", exc)


def _fetch_live_rate() -> Tuple[float, str]:
    response = requests.get(FRANKFURTER_URL, timeout=15)
    response.raise_for_status()
    payload = response.json()
    rate = float(payload["rates"]["HUF"])
    rate_date = str(payload.get("date") or date.today().isoformat())
    return rate, rate_date


def get_eur_to_huf_rate() -> float:
    """Return EUR→HUF rate, refreshed once per day from ECB data (Frankfurter API)."""
    today = date.today().isoformat()
    cached = _read_cache()
    if cached and cached.get("date") == today:
        rate = float(cached["rate"])
        logger.info("Using cached EUR/HUF rate: %.2f (date %s)", rate, today)
        return rate

    try:
        rate, rate_date = _fetch_live_rate()
        _write_cache(rate, rate_date)
        logger.info("Fetched EUR/HUF rate: %.2f (date %s)", rate, rate_date)
        return rate
    except Exception as exc:
        if cached and "rate" in cached:
            rate = float(cached["rate"])
            logger.warning(
                "Exchange-rate fetch failed (%s); using stale cache: %.2f (date %s)",
                exc,
                rate,
                cached.get("date"),
            )
            return rate
        logger.warning(
            "Exchange-rate fetch failed (%s); using fallback EUR/HUF rate: %.2f",
            exc,
            FALLBACK_RATE,
        )
        return FALLBACK_RATE
