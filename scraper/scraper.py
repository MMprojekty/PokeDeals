import argparse
import asyncio
import json
import logging
import os
import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote_plus
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from playwright.async_api import Browser, Error, Page, async_playwright
from exchange_rate import get_eur_to_huf_rate
from supabase import Client, create_client

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv:
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("pokedeals-scraper")

SUPPORTED_CATEGORIES = {
    "Booster-Boxes",
    "Elite-Trainer-Boxes",
    "Box-Sets",
    "Tins",
    "Blisters",
    "Boosters",
}
EUR_TO_HUF_RATE = 395.0
LISTINGS_TABLE = os.getenv("SUPABASE_LISTINGS_TABLE", "shop_listings")
STATS_BUCKET = "pokedeals-meta"
STATS_OBJECT = "stats_snapshots.json"
MAX_STATS_SNAPSHOTS = 30
DELETE_SENTINEL_ID = "00000000-0000-0000-0000-000000000000"
MIN_EXPECTED_PRODUCTS = int(os.getenv("MIN_EXPECTED_PRODUCTS", "30"))

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "hu-HU,hu;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

ANTIBOT_MARKERS = (
    "please confirm you are human",
    "enable javascript and cookies to continue",
    "cf-challenge-running",
    "checking your browser before accessing",
    "attention required! | cloudflare",
    "just a moment...",
    "ez az oldal jelenleg nem elérhető",
)

CATEGORY_HINTS = {
    "Booster-Boxes": {"booster_box"},
    "Elite-Trainer-Boxes": {"etb"},
    "Box-Sets": {"bundle", "box_set"},
    "Tins": {"tin"},
    "Blisters": {"blister"},
    "Boosters": {"booster_pack"},
}


@dataclass(frozen=True)
class ShopConfig:
    name: str
    url: str
    card_sel: str
    title_sel: str
    price_sel: str
    base_url: str
    cookie_btn: Optional[str] = None
    out_of_stock_class: str = ""
    out_of_stock_text: str = ""
    next_btn: str = ""


def require_env(var_name: str) -> str:
    value = os.getenv(var_name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {var_name}")
    return value


def send_alert(message: str, details: Optional[Dict[str, object]] = None) -> None:
    webhook_url = os.getenv("ALERT_WEBHOOK_URL", "").strip()
    if not webhook_url:
        return
    payload = {
        "text": f"[PokeDeals scraper] {message}",
        "details": details or {},
        "ts": int(time.time()),
    }
    try:
        requests.post(webhook_url, json=payload, timeout=10)
    except Exception as exc:
        logger.warning("Alert webhook failed: %s", exc)


def get_clients(use_ai_matching: bool = True) -> Tuple[Client, Optional[OpenAI]]:
    supabase_url = require_env("SUPABASE_URL")
    supabase_key = require_env("SUPABASE_SERVICE_ROLE_KEY")
    supabase_client = create_client(supabase_url, supabase_key)
    if not use_ai_matching:
        return supabase_client, None

    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not openai_key:
        logger.warning("OPENAI_API_KEY missing, AI matching disabled.")
        return supabase_client, None
    return supabase_client, OpenAI(api_key=openai_key)


def validate_required_env_vars(use_ai_matching: bool = True) -> List[str]:
    required_vars = ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"]
    if use_ai_matching:
        required_vars.append("OPENAI_API_KEY")
    missing = []
    for key in required_vars:
        value = os.getenv(key, "").strip()
        if not value:
            missing.append(key)
            continue
        lowered = value.lower()
        if lowered.startswith("your-") or "replace-me" in lowered:
            missing.append(key)
    return missing


def clean_price(price_text: Optional[str]) -> int:
    """Parse Hungarian prices: '24 990 Ft', '24.990 Ft', '24990 HUF', '24 990,- Ft'."""
    if not price_text:
        return 0
    normalized = (
        price_text.replace("\u00a0", " ")
        .replace("HUF", "")
        .replace("huf", "")
        .replace("Ft", "")
        .replace("ft", "")
        .strip()
    )
    # Drop trailing decimal part if present (rare on HU shops).
    normalized = normalized.split(",")[0]
    digits = "".join(ch for ch in normalized if ch.isdigit())
    return int(digits) if digits else 0


def is_allowed_product_title(title: str) -> bool:
    text = normalize_text(title)
    blocked_terms = [
        "live breaking",
        "pack break",
        "futera",
        "yugioh",
        "yu-gi-oh",
        "magic the gathering",
        "lorcana",
        "one piece",
        "sport",
    ]
    return not any(term in text for term in blocked_terms)


def parse_eur_to_huf(price_text: str) -> Optional[int]:
    cleaned = price_text.replace("€", "").replace(".", "").replace(",", ".").strip()
    try:
        return int(float(cleaned) * EUR_TO_HUF_RATE)
    except (TypeError, ValueError):
        return None


HU_SEALED_HINTS = {
    "booster_box": {
        "booster box",
        "booster doboz",
        "bontatlan doboz",
        "display",
        "display box",
        "booster display",
    },
    "bundle": {"booster bundle", "bundle", "booster csomag"},
    "booster_pack": {"booster pack", "booster csomag", "kiegeszito csomag", "kiegészítő csomag"},
    "etb": {"elite trainer box", " etb", "etb "},
    "tin": {"tin", "femdoboz", "fémdoboz", "metal box"},
    "blister": {"bliszter", "blister", "premium kollekcio", "prémium kollekció", "diszdoboz", "díszdoboz"},
    "box_set": {"collection box", "kollekcios doboz", "kollekciós doboz", "box set"},
}


def detect_product_signals(title: str) -> set:
    text = normalize_text(title)
    signals = set()

    for signal, hints in HU_SEALED_HINTS.items():
        if any(hint in text for hint in hints):
            signals.add(signal)

    # English fallbacks when Hungarian hints are absent.
    if "booster box" in text or "display" in text:
        signals.add("booster_box")
    if "booster bundle" in text or ("bundle" in text and "booster" in text):
        signals.add("bundle")
    if "booster pack" in text or ("pack" in text and "booster" in text):
        signals.add("booster_pack")
    if "elite trainer box" in text or " etb" in f" {text}":
        signals.add("etb")
    if "tin" in text:
        signals.add("tin")
    if "blister" in text:
        signals.add("blister")
    if (
        "box" in text
        and "booster box" not in text
        and "elite trainer box" not in text
        and "booster_pack" not in signals
    ):
        signals.add("box_set")

    return signals


def mapping_is_consistent(local_title: str, cm_name: str, cm_category: str) -> bool:
    source_signals = detect_product_signals(local_title)
    mapped_signals = detect_product_signals(cm_name)
    expected = CATEGORY_HINTS.get(cm_category, set())

    # If source strongly indicates a format, category must be compatible.
    strong_source = source_signals.intersection({"booster_box", "bundle", "booster_pack", "etb", "tin", "blister"})
    if strong_source and not (strong_source & expected):
        return False

    # Prevent classic wrong mapping: bundle source -> booster box output.
    if "bundle" in source_signals and "booster_box" in mapped_signals:
        return False
    if "booster_pack" in source_signals and "booster_box" in mapped_signals:
        return False

    return True


def stabilize_canonical_title(title: str) -> str:
    cleaned = title.strip()
    replacements = [
        (r"^pok[eé]mon\s*tcg[:\-\s–—]*", ""),
        (r"^pok[eé]mon[:\-\s–—]*", ""),
        (r"\bdisplay box\b", "booster box"),
        (r"\bbooster display\b", "booster box"),
        (r"\s*\(\s*\d+\s*packs?\s*\)\s*", " "),
        (r"\s*\(\s*36\s*booster[s]?\s*\)\s*", " "),
        (r"\s*\(\s*bundle\s*\)\s*", " booster bundle "),
    ]
    for pattern, repl in replacements:
        cleaned = re.sub(pattern, repl, cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^[\s\-–—:]+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -–—:")
    return cleaned


def extract_identity_tokens(title: str) -> set:
    text = normalize_text(title)
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    tokens = [t for t in text.split() if t]
    stop = {
        "pokemon", "tcg", "trading", "card", "game", "mega", "evolution",
        "booster", "box", "bundle", "pack", "elite", "trainer", "tin",
        "blister", "english", "angol", "hungarian", "magyar", "edition",
        "display", "premium", "collection",
    }
    return {t for t in tokens if t not in stop and len(t) > 2}


def canonical_title_is_specific(source_title: str, canonical_title: str) -> bool:
    generic_patterns = [
        r"^elite trainer box$",
        r"^booster box$",
        r"^booster bundle$",
        r"^booster pack$",
        r"^tin$",
        r"^blister$",
        r"^premium collection$",
        r"^box$",
    ]
    canon_norm = normalize_text(canonical_title).strip()
    if any(re.match(p, canon_norm) for p in generic_patterns):
        return False

    source_tokens = extract_identity_tokens(source_title)
    canonical_tokens = extract_identity_tokens(canonical_title)
    if source_tokens and not (source_tokens & canonical_tokens):
        return False
    return True


def ai_canonicalize_title(ai_client: OpenAI, local_title: str) -> Tuple[bool, Optional[str]]:
    prompt = f"""
You normalize Hungarian webshop titles for Pokemon sealed products.

Input title: "{local_title}"

Rules:
1) If not a Pokemon TCG product OR not a sealed product, return is_valid=false.
2) Keep product type accurate (Booster Box, Booster Bundle, Booster Pack, ETB, Tin, Blister, Box).
3) Canonical title must be concise, stable across shops, and in English.
4) Canonical title MUST include set/series identity (for example "Perfect Order", "Journey Together", "151", etc).
5) Never return generic labels like "Elite Trainer Box" alone.
6) Never start the title with punctuation, dashes, or "Pokemon"/"Pokemon TCG".
7) Do not transform Bundle into Booster Box or Pack into Box.

Return JSON only:
{{
  "is_valid": boolean,
  "canonical_title": "string"
}}
"""
    try:
        response = ai_client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        parsed = json.loads(response.choices[0].message.content)
        if not parsed.get("is_valid"):
            return False, None
        canonical = (parsed.get("canonical_title") or "").strip()
        if not canonical:
            return False, None
        canonical = stabilize_canonical_title(canonical)
        if not canonical_title_is_specific(local_title, canonical):
            return False, None
        return True, canonical
    except Exception as exc:
        logger.warning("AI canonicalization failed for '%s': %s", local_title, exc)
        return False, None


def ai_normalize_title(ai_client: OpenAI, local_title: str) -> Tuple[Optional[str], Optional[str], int]:
    prompt = f"""
You are a Pokemon TCG expert data extractor. Look at this webshop title: "{local_title}"

Rules:
1. If product is Japanese, Korean, or non-English, respond with {{"is_valid": false}}.
2. If product is a single card, a coin, deck sleeves, or accessories-only item, respond with {{"is_valid": false}}.
3. If product is an English SEALED product, translate/normalize it to official Cardmarket product naming.
4. cardmarket_category must be one of: Booster-Boxes, Elite-Trainer-Boxes, Box-Sets, Tins, Blisters, Boosters

Return only valid JSON with this shape:
{{
  "is_valid": boolean,
  "cardmarket_name": "string",
  "cardmarket_category": "string",
  "demand_score": integer
}}
"""
    try:
        response = ai_client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        result = json.loads(response.choices[0].message.content)
        is_valid = bool(result.get("is_valid"))
        if not is_valid:
            return None, None, 0

        cm_name = (result.get("cardmarket_name") or "").strip()
        cm_category = (result.get("cardmarket_category") or "").strip()
        demand_score = result.get("demand_score", 50)
        if not cm_name or cm_category not in SUPPORTED_CATEGORIES:
            return None, None, 0
        if not mapping_is_consistent(local_title, cm_name, cm_category):
            logger.info("Rejected inconsistent AI mapping: '%s' -> '%s' (%s)", local_title, cm_name, cm_category)
            return None, None, 0

        if not isinstance(demand_score, int):
            demand_score = 50
        demand_score = max(0, min(demand_score, 100))
        return cm_name, cm_category, demand_score
    except Exception as exc:
        logger.warning("AI normalization failed for '%s': %s", local_title, exc)
        return None, None, 0


def build_cm_url(product_name: str, category: str) -> str:
    clean_name = product_name.replace("&", "").replace(":", "").replace("'", "")
    clean_name = re.sub(r"[^a-zA-Z0-9\s-]", "", clean_name)
    slug = re.sub(r"\s+", "-", clean_name.strip())
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return f"https://www.cardmarket.com/en/Pokemon/Products/{category}/{quote_plus(slug)}"


def fetch_cm_prices(scraper_api_key: str, url: str) -> Dict[str, Optional[int]]:
    # NOTE: On some macOS Python/LibreSSL setups, HTTPS to ScraperAPI fails with SSLEOFError.
    # Using HTTP for the proxy endpoint avoids the local TLS handshake issue while ScraperAPI
    # still fetches the target HTTPS URL server-side.
    scraper_api_url = f"http://api.scraperapi.com?api_key={scraper_api_key}&url={quote_plus(url)}"
    try:
        response = requests.get(scraper_api_url, timeout=60)
        if response.status_code != 200:
            if (
                response.status_code == 403
                and "exhausted the api credits" in response.text.lower()
            ):
                logger.error("ScraperAPI credits exhausted. Cardmarket enrichment is unavailable until quota resets/upgrades.")
            return {"cm30": None, "cm7": None}

        soup = BeautifulSoup(response.text, "html.parser")
        cm30 = None
        cm7 = None
        for dt, dd in zip(soup.find_all("dt"), soup.find_all("dd")):
            dt_text = dt.text.strip()
            dd_text = dd.text.strip()
            if "Price Trend" in dt_text:
                cm30 = parse_eur_to_huf(dd_text)
            elif "7-days" in dt_text:
                cm7 = parse_eur_to_huf(dd_text)

        # Cardmarket layouts vary; fallback to regex extraction from full page text.
        if cm30 is None or cm7 is None:
            page_text = soup.get_text(" ", strip=True)

            def extract_after_label(pattern: str) -> Optional[int]:
                m = re.search(pattern, page_text, flags=re.IGNORECASE)
                if not m:
                    return None
                return parse_eur_to_huf(m.group(1))

            if cm30 is None:
                cm30 = extract_after_label(r"(?:Price Trend|30-days average price)\s*([0-9]+(?:[.,][0-9]{3})*(?:[.,][0-9]{1,2})?\s*€)")
            if cm7 is None:
                cm7 = extract_after_label(r"(?:7-days average price|7-days)\s*([0-9]+(?:[.,][0-9]{3})*(?:[.,][0-9]{1,2})?\s*€)")
        return {"cm30": cm30, "cm7": cm7}
    except Exception as exc:
        logger.warning("Cardmarket fetch failed (%s): %s", url, exc)
        return {"cm30": None, "cm7": None}


def find_cardmarket_product_url(scraper_api_key: str, product_name: str, category: str) -> Optional[str]:
    search_url = (
        "https://www.cardmarket.com/en/Pokemon/Products/Search?searchString="
        f"{quote_plus(product_name)}"
    )
    scraper_api_url = f"http://api.scraperapi.com?api_key={scraper_api_key}&url={quote_plus(search_url)}"
    try:
        response = requests.get(scraper_api_url, timeout=60)
        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        tokens = [t for t in re.findall(r"[a-z0-9]+", product_name.lower()) if len(t) > 2]
        best_url = None
        best_score = 0

        for link in soup.select("a[href*='/en/Pokemon/Products/']"):
            href = link.get("href") or ""
            if f"/Products/{category}/" not in href:
                continue
            label = " ".join(link.get_text(" ", strip=True).lower().split())
            score = sum(1 for token in tokens if token in label)
            if score > best_score:
                best_score = score
                best_url = href

        if not best_url:
            return None
        if best_url.startswith("http"):
            return best_url
        return f"https://www.cardmarket.com{best_url}"
    except Exception as exc:
        logger.warning("Cardmarket search failed (%s): %s", product_name, exc)
        return None


def build_cardmarket_query_variants(product_name: str) -> List[str]:
    variants = [product_name.strip()]
    simplified = product_name
    cleanup_patterns = [
        r"^pok[eé]mon\s*tcg[:\-\s]*",
        r"^pok[eé]mon[:\-\s]*",
        r"^scarlet\s*&\s*violet\s*\d+[:\-\s]*",
        r"^mega evolution\s*\d+(\.\d+)?[:\-\s]*",
        r"\s*\(\s*bundle\s*\)\s*$",
    ]
    for pattern in cleanup_patterns:
        simplified = re.sub(pattern, "", simplified, flags=re.IGNORECASE).strip()
    simplified = re.sub(r"\s+", " ", simplified).strip(" -:")
    if simplified and simplified.lower() != variants[0].lower():
        variants.append(simplified)

    # Product type-specific hint variants improve search hit rate.
    lower = simplified.lower() if simplified else product_name.lower()
    if "pack" in lower and "booster pack" not in lower:
        variants.append(f"{simplified} Booster Pack".strip())
    if "box" in lower and "booster box" not in lower and "elite trainer box" not in lower:
        variants.append(f"{simplified} Box".strip())

    deduped = []
    seen = set()
    for v in variants:
        key = v.lower()
        if v and key not in seen:
            seen.add(key)
            deduped.append(v)
    return deduped


def scrape_cardmarket_prices(scraper_api_key: str, product_name: str, category: str) -> Dict[str, Optional[int]]:
    query_variants = build_cardmarket_query_variants(product_name)
    for candidate in query_variants:
        first_try = fetch_cm_prices(scraper_api_key, build_cm_url(candidate, category))
        if first_try["cm30"] is not None:
            return first_try

        # Fallback to Cardmarket search page when slug guessing misses.
        search_match_url = find_cardmarket_product_url(scraper_api_key, candidate, category)
        if search_match_url:
            searched = fetch_cm_prices(scraper_api_key, search_match_url)
            if searched["cm30"] is not None:
                return searched

    if "bundle" in product_name.lower():
        alt_category = "Booster-Boxes" if category == "Box-Sets" else "Box-Sets"
        logger.info("Trying fallback category %s for %s", alt_category, product_name)
        for candidate in query_variants:
            alt_prices = fetch_cm_prices(scraper_api_key, build_cm_url(candidate, alt_category))
            if alt_prices["cm30"] is not None:
                return alt_prices
            alt_search_url = find_cardmarket_product_url(scraper_api_key, candidate, alt_category)
            if alt_search_url:
                alt_found = fetch_cm_prices(scraper_api_key, alt_search_url)
                if alt_found["cm30"] is not None:
                    return alt_found

    return {"cm30": None, "cm7": None}


def get_shop_configs() -> List[ShopConfig]:
    return [
        ShopConfig(
            name="Myth Games",
            url="https://mythgames.eu/collections/pokemon-kartyak-booster-boxok-es-gyujtoi-termekek",
            card_sel="hdt-card-product",
            title_sel=".hdt-card-product__title",
            price_sel=".hdt-price-wrapp",
            out_of_stock_class="sold_out",
            next_btn="a[aria-label='Next']",
            base_url="https://mythgames.eu",
        ),
        ShopConfig(
            name="Metagames",
            url="https://www.metagames.hu/gyujtogetos-kartyajatekok/pokemon-tcg",
            card_sel=".webshop-list-item",
            title_sel=".webshop-list-item-name",
            price_sel="h5.font-weight-bold",
            out_of_stock_text="nincs készleten",
            cookie_btn="text='Mind elfogad'",
            next_btn="a.page-link[title='Go to next page']",
            base_url="https://www.metagames.hu",
        ),
        ShopConfig(
            name="SportKartyabolt",
            url="https://sportkartyabolt.hu/Pokemon-Kartya",
            card_sel=".product",
            title_sel="h2",
            price_sel="[class*=price]",
            out_of_stock_text="nincs raktaron",
            next_btn="a.next",
            base_url="https://sportkartyabolt.hu",
        ),
        ShopConfig(
            name="Reflexshop",
            url="https://reflexshop.hu/Tarsasjatekok/Gyujtoi-kartyak/Pokemon",
            card_sel=".product-card",
            title_sel=".name-link",
            price_sel=".sale-price, .price",
            out_of_stock_text="nem rendelheto",
            next_btn="a.next",
            base_url="https://reflexshop.hu",
        ),
        ShopConfig(
            name="Pokedom",
            url="https://www.pokedom.hu/pokemon-183",
            card_sel=".product-card",
            title_sel="h3",
            price_sel=".product-price",
            out_of_stock_text="nincs raktaron",
            next_btn=".pagination-next",
            base_url="https://www.pokedom.hu",
        ),
        ShopConfig(
            name="CollectKing",
            url="https://collectking.hu/termekkategoria/pokemon/",
            card_sel="li.product",
            title_sel=".woocommerce-loop-product__title",
            price_sel=".price",
            out_of_stock_text="elfogyott",
            next_btn="a.next",
            base_url="https://collectking.hu",
        ),
        ShopConfig(
            name="TCGFutar",
            url="https://tcgfutar.hu/spl/100003/Pokemon-TCG",
            card_sel=".product.js-product",
            title_sel=".product__name-link, h2.product__name, a[title]",
            price_sel=".product__price-base, .product__prices",
            out_of_stock_text="elfogyott",
            next_btn="a.next",
            base_url="https://tcgfutar.hu",
        ),
        ShopConfig(
            name="Xzone",
            url="https://www.xzone.hu/sberatelske-hry-pokemon-tcg?s=60",
            card_sel=".product-item",
            title_sel=".product-item-name a",
            price_sel=".price",
            out_of_stock_text="nincs keszleten",
            next_btn=".pagination__next",
            base_url="https://www.xzone.hu",
        ),
        ShopConfig(
            name="TCGBolt",
            url="https://tcgbolt.hu/termekkategoria/pokemon/",
            card_sel="li.product",
            title_sel=".woocommerce-loop-product__title",
            price_sel=".price",
            out_of_stock_class="outofstock",
            out_of_stock_text="elfogyott",
            next_btn="a.next",
            base_url="https://tcgbolt.hu",
        ),
        ShopConfig(
            name="MomokoShop",
            url="https://momokoshop.hu/shop/pokemon-kartya-kollekcio",
            card_sel="li.product",
            title_sel="h3",
            price_sel=".price",
            out_of_stock_class="outofstock",
            out_of_stock_text="elfogyott",
            next_btn="a.next",
            base_url="https://momokoshop.hu",
        ),
        ShopConfig(
            name="TCGCenter",
            url="https://tcgcenter.hu/",
            card_sel="li.product",
            title_sel=".woocommerce-loop-product__title",
            price_sel=".price",
            out_of_stock_class="outofstock",
            out_of_stock_text="elfogyott",
            next_btn="a.next",
            base_url="https://tcgcenter.hu",
        ),
        ShopConfig(
            name="PottyosZebra",
            url="https://pottyoszebra.hu/termekkategoria/gyujtogetos-kartyajatekok-tcg/pokemon-trading-card-game-tcg/",
            card_sel="li.product",
            title_sel=".woocommerce-loop-product__title",
            price_sel=".price",
            next_btn="a.next",
            base_url="https://pottyoszebra.hu",
        ),
        ShopConfig(
            name="Zozoshop",
            url="https://zozoshop.hu/pokemon-gyujtheto-kartyak-tcg/pokemon-booster-packs",
            card_sel="div.card.product-card",
            title_sel=".product-card-title a",
            price_sel=".product-price",
            base_url="https://zozoshop.hu",
        ),
        ShopConfig(
            name="VarazslatosJatekok",
            url="https://www.varazslatosjatekok.hu/pokemon-booster-boxok/",
            card_sel="[data-testid='productItem']",
            title_sel="span[data-testid='productCardName']",
            price_sel="div[data-testid='productCardPrice']",
            base_url="https://www.varazslatosjatekok.hu",
        ),
    ]


def normalize_text(value: str) -> str:
    return (
        value.lower()
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ö", "o")
        .replace("ő", "o")
        .replace("ú", "u")
        .replace("ü", "u")
        .replace("ű", "u")
    )


def normalize_url(base_url: str, link: Optional[str]) -> str:
    if not link:
        return ""
    return urljoin(base_url, link)


PRODUCT_LINK_SELECTORS = (
    "a.woocommerce-loop-product__link",
    "a.woocommerce-LoopProduct-link",
    "a.product__name-link",
    "a.product_link_normal",
    "a.name-link",
    ".product-item-name a",
    ".woocommerce-loop-product__title a",
    "h3 a",
    "h2 a",
)


def is_cart_or_junk_url(href: Optional[str]) -> bool:
    lowered = (href or "").lower()
    junk_markers = (
        "add-to-cart",
        "add_to_cart",
        "/kosar",
        "/cart",
        "ajax_add_to_cart",
        "javascript:",
        "#",
    )
    return not lowered or any(marker in lowered for marker in junk_markers)


def read_price_text(price_el) -> str:
    if not price_el:
        return ""
    sale_el = price_el.select_one("ins .amount, ins")
    if sale_el:
        return sale_el.get_text(strip=True)
    return price_el.get_text(strip=True)


def pick_product_url_bs(card, base_url: str, title_sel: str) -> str:
    for sel in PRODUCT_LINK_SELECTORS:
        link = card.select_one(sel)
        href = link.get("href") if link else None
        if href and not is_cart_or_junk_url(href):
            return normalize_url(base_url, href)

    for part in title_sel.split(","):
        part = part.strip()
        if not part:
            continue
        title_el = card.select_one(part)
        if not title_el:
            continue
        if title_el.name == "a":
            href = title_el.get("href")
            if href and not is_cart_or_junk_url(href):
                return normalize_url(base_url, href)
        nested = title_el.select_one("a[href]")
        if nested:
            href = nested.get("href")
            if href and not is_cart_or_junk_url(href):
                return normalize_url(base_url, href)

    for link in card.select("a[href]"):
        href = link.get("href")
        if href and not is_cart_or_junk_url(href):
            return normalize_url(base_url, href)
    return ""


async def pick_product_url_pw(card, config: ShopConfig) -> str:
    for sel in PRODUCT_LINK_SELECTORS:
        link = await card.query_selector(sel)
        if not link:
            continue
        href = await link.get_attribute("href")
        if href and not is_cart_or_junk_url(href):
            return normalize_url(config.base_url, href)

    for part in config.title_sel.split(","):
        part = part.strip()
        if not part:
            continue
        title_el = await card.query_selector(part)
        if not title_el:
            continue
        tag = await title_el.evaluate("el => el.tagName.toLowerCase()")
        if tag == "a":
            href = await title_el.get_attribute("href")
            if href and not is_cart_or_junk_url(href):
                return normalize_url(config.base_url, href)
        nested = await title_el.query_selector("a[href]")
        if nested:
            href = await nested.get_attribute("href")
            if href and not is_cart_or_junk_url(href):
                return normalize_url(config.base_url, href)

    links = await card.query_selector_all("a[href]")
    for link in links:
        href = await link.get_attribute("href")
        if href and not is_cart_or_junk_url(href):
            return normalize_url(config.base_url, href)
    return ""


async def read_price_text_pw(price_el) -> str:
    if not price_el:
        return ""
    sale_el = await price_el.query_selector("ins .amount, ins")
    if sale_el:
        return ((await sale_el.text_content()) or "").strip()
    return ((await price_el.text_content()) or "").strip()


def is_antibot_html(html: str) -> bool:
    lowered = (html or "").lower()
    return any(marker in lowered for marker in ANTIBOT_MARKERS)


def fetch_html(url: str, timeout_s: int = 30) -> str:
    response = requests.get(url, headers=REQUEST_HEADERS, timeout=timeout_s)
    response.raise_for_status()
    return response.text


def select_first_match(parent, selector: str):
    for part in selector.split(","):
        part = part.strip()
        if not part:
            continue
        match = parent.select_one(part)
        if match:
            return match
    return None


def read_title_text(title_el) -> str:
    if not title_el:
        return ""
    text = title_el.get_text(strip=True)
    if text:
        return text
    return (title_el.get("title") or "").strip()


def card_is_out_of_stock(card_class: str, card_text: str, config: ShopConfig) -> bool:
    generic_out_of_stock_signals = (
        "outofstock",
        "sold out",
        "soldout",
        "elfogyott",
        "nincs keszleten",
        "nincs raktaron",
        "nem rendelheto",
        "currently unavailable",
    )
    if any(signal in card_class or signal in card_text for signal in generic_out_of_stock_signals):
        return True
    if config.out_of_stock_class and config.out_of_stock_class.lower() in card_class:
        return True
    if config.out_of_stock_text and normalize_text(config.out_of_stock_text) in card_text:
        return True
    return False


def extract_card_data_http(card, config: ShopConfig) -> Optional[Dict[str, object]]:
    card_class = " ".join(card.get("class", [])).lower()
    card_text = normalize_text(card.get_text(" ", strip=True))
    if card_is_out_of_stock(card_class, card_text, config):
        return None

    title_el = select_first_match(card, config.title_sel)
    price_el = select_first_match(card, config.price_sel)
    if not title_el or not price_el:
        return None

    raw_title = read_title_text(title_el)
    price_huf = clean_price(read_price_text(price_el))
    if not raw_title or price_huf <= 0:
        return None
    if not is_allowed_product_title(raw_title):
        return None

    image_url = ""
    img_el = card.select_one("img")
    if img_el:
        for attr in ("src", "data-src", "data-lazy-src"):
            image_url = normalize_url(config.base_url, img_el.get(attr))
            if image_url and "space.gif" not in image_url:
                break

    product_url = pick_product_url_bs(card, config.base_url, config.title_sel)

    return {
        "shop_name": config.name,
        "raw_title": raw_title,
        "price_huf": price_huf,
        "stock_status": "IN_STOCK",
        "product_url": product_url,
        "image_url": image_url,
    }


def scrape_shop_http(config: ShopConfig) -> List[Dict[str, object]]:
    logger.info("%s: trying HTTP fallback", config.name)
    scraped_data: List[Dict[str, object]] = []
    seen_titles = set()
    page_url = config.url

    for _ in range(12):
        try:
            html = fetch_html(page_url)
        except Exception as exc:
            logger.warning("%s: HTTP fetch failed for %s: %s", config.name, page_url, exc)
            break

        if is_antibot_html(html):
            logger.warning("%s: possible anti-bot page on HTTP (still parsing)", config.name)

        soup = BeautifulSoup(html, "html.parser")
        product_cards = soup.select(config.card_sel)
        if not product_cards:
            break

        for card in product_cards:
            item = extract_card_data_http(card, config)
            if not item:
                continue
            dedupe_key = (item["shop_name"], item["raw_title"], item["price_huf"])
            if dedupe_key in seen_titles:
                continue
            seen_titles.add(dedupe_key)
            scraped_data.append(item)

        if not config.next_btn:
            break

        next_link = soup.select_one(config.next_btn)
        next_href = next_link.get("href") if next_link else None
        if not next_href:
            break
        page_url = normalize_url(config.base_url, next_href)
        if not page_url:
            break

    logger.info("%s: HTTP fallback found %d products", config.name, len(scraped_data))
    return scraped_data


def image_url_score(image_url: str, title: str) -> int:
    if not image_url:
        return -10_000

    url = normalize_text(image_url)
    title_tokens = [
        token
        for token in re.sub(r"[^a-z0-9 ]+", " ", normalize_text(title)).split()
        if len(token) > 3
    ]

    score = 0
    if re.search(r"\.(jpg|jpeg|png|webp)(\?|$)", url):
        score += 12
    if any(key in url for key in ("product", "products", "termek", "pokemon")):
        score += 10
    if any(key in url for key in ("booster", "trainer", "etb", "tin", "blister", "box")):
        score += 6

    bad_markers = (
        "shipping",
        "szallitas",
        "ingyenes",
        "free-shipping",
        "logo",
        "icon",
        "badge",
        "banner",
        "placeholder",
        "no-image",
    )
    if any(marker in url for marker in bad_markers):
        score -= 60

    for token in title_tokens[:8]:
        if token in url:
            score += 2
    return score


async def pick_best_image_url(card, config: ShopConfig, title: str) -> str:
    candidates: List[str] = []
    img_elements = await card.query_selector_all("img")
    for img_el in img_elements:
        src = await img_el.get_attribute("src")
        data_src = await img_el.get_attribute("data-src")
        lazy_src = await img_el.get_attribute("data-lazy-src")
        srcset = await img_el.get_attribute("srcset")
        for raw in (src, data_src, lazy_src):
            normalized = normalize_url(config.base_url, raw)
            if normalized:
                candidates.append(normalized)
        if srcset:
            # Keep first srcset URL candidate.
            first = srcset.split(",")[0].strip().split(" ")[0].strip()
            normalized = normalize_url(config.base_url, first)
            if normalized:
                candidates.append(normalized)

    if not candidates:
        return ""

    unique_candidates = list(dict.fromkeys(candidates))
    best = max(unique_candidates, key=lambda url: image_url_score(url, title))
    if image_url_score(best, title) < -20:
        return ""
    return best


async def extract_card_data(card, config: ShopConfig) -> Optional[Dict[str, object]]:
    try:
        card_class = (await card.get_attribute("class") or "").lower()
        card_text = normalize_text((await card.inner_text() or ""))
        if card_is_out_of_stock(card_class, card_text, config):
            return None

        title_el = await card.query_selector(config.title_sel.split(",")[0].strip())
        if not title_el:
            for part in config.title_sel.split(","):
                part = part.strip()
                if part:
                    title_el = await card.query_selector(part)
                    if title_el:
                        break
        price_el = await card.query_selector(config.price_sel.split(",")[0].strip())
        if not price_el:
            for part in config.price_sel.split(","):
                part = part.strip()
                if part:
                    price_el = await card.query_selector(part)
                    if price_el:
                        break
        if not title_el or not price_el:
            return None

        raw_title = ((await title_el.text_content()) or "").strip()
        if not raw_title:
            raw_title = ((await title_el.get_attribute("title")) or "").strip()
        price_huf = clean_price(await read_price_text_pw(price_el))
        if not raw_title or price_huf <= 0:
            return None
        if not is_allowed_product_title(raw_title):
            return None

        image_url = await pick_best_image_url(card, config, raw_title)

        product_url = await pick_product_url_pw(card, config)

        return {
            "shop_name": config.name,
            "raw_title": raw_title,
            "price_huf": price_huf,
            "stock_status": "IN_STOCK",
            "product_url": product_url,
            "image_url": image_url,
        }
    except Error:
        return None
    except Exception as exc:
        logger.debug("Card parse error on %s: %s", config.name, exc)
        return None


async def scroll_page(page: Page, steps: int = 4, delay_ms: int = 800) -> None:
    for _ in range(steps):
        await page.evaluate("window.scrollBy(0, 900)")
        await page.wait_for_timeout(delay_ms)


async def scrape_shop(page: Page, config: ShopConfig) -> List[Dict[str, object]]:
    logger.info("Scraping %s", config.name)
    blocked = False
    try:
        await page.goto(config.url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(1500)
    except Exception as exc:
        logger.warning("Failed to open %s: %s", config.name, exc)
        return scrape_shop_http(config)

    try:
        html = await page.content() or ""
        if is_antibot_html(html):
            logger.warning("%s: possible anti-bot challenge in browser (continuing anyway).", config.name)
            blocked = True
    except Exception:
        pass

    if config.cookie_btn:
        try:
            await page.click(config.cookie_btn, timeout=3000)
        except Exception:
            pass

    scraped_data: List[Dict[str, object]] = []
    seen_titles = set()
    last_signature = None
    retried_empty_once = False

    while True:
        await scroll_page(page)
        product_cards = await page.query_selector_all(config.card_sel)
        if not product_cards:
            if not retried_empty_once:
                retried_empty_once = True
                logger.info("%s: no cards found, retrying page load once...", config.name)
                try:
                    await page.reload(wait_until="networkidle", timeout=60000)
                    await page.wait_for_timeout(2500)
                    continue
                except Exception:
                    pass
            break

        first_text = await product_cards[0].inner_text()
        if first_text == last_signature:
            break
        last_signature = first_text

        for card in product_cards:
            item = await extract_card_data(card, config)
            if not item:
                continue

            dedupe_key = (item["shop_name"], item["raw_title"], item["price_huf"])
            if dedupe_key in seen_titles:
                continue
            seen_titles.add(dedupe_key)
            scraped_data.append(item)

        if not config.next_btn:
            break

        next_button = await page.query_selector(config.next_btn)
        if not next_button:
            break
        try:
            await next_button.click(force=True)
            await page.wait_for_load_state("domcontentloaded", timeout=60000)
        except Exception:
            break

    if not scraped_data or blocked:
        http_rows = scrape_shop_http(config)
        if len(http_rows) > len(scraped_data):
            return http_rows

    logger.info("%s: %d products", config.name, len(scraped_data))
    return scraped_data


def canonical_key_for_grouping(name: str) -> str:
    """Mirror web/lib/listings.ts canonicalKey for consistent product counts."""
    text = unicodedata.normalize("NFD", name)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.lower()
    text = re.sub(r"pokemon\s*tcg[:\-\s]*", " ", text)
    text = re.sub(r"pokemon[:\-\s]*", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def compute_run_stats(items: List[Dict[str, object]]) -> Dict[str, int]:
    product_keys = set()
    shops = set()
    for item in items:
        title = str(item.get("raw_title", "")).strip()
        shop = str(item.get("shop_name", "")).strip()
        if title:
            product_keys.add(canonical_key_for_grouping(title))
        if shop:
            shops.add(shop)
    return {
        "in_stock_products": len(product_keys),
        "shops_count": len(shops),
        "in_stock_offers": len(items),
    }


def store_stats_snapshot(supabase_client: Client, stats: Dict[str, int]) -> None:
    def _do() -> None:
        try:
            supabase_client.storage.get_bucket(STATS_BUCKET)
        except Exception:
            try:
                supabase_client.storage.create_bucket(STATS_BUCKET, options={"public": False})
            except Exception:
                pass

        snapshots: List[Dict[str, object]] = []
        try:
            raw = supabase_client.storage.from_(STATS_BUCKET).download(STATS_OBJECT)
            payload = json.loads(raw.decode("utf-8"))
            if isinstance(payload, dict) and isinstance(payload.get("snapshots"), list):
                snapshots = payload["snapshots"]
        except Exception:
            snapshots = []

        snapshots.append(
            {
                "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                **stats,
            }
        )
        snapshots = snapshots[-MAX_STATS_SNAPSHOTS:]
        body = json.dumps({"snapshots": snapshots}).encode("utf-8")
        supabase_client.storage.from_(STATS_BUCKET).upload(
            STATS_OBJECT,
            body,
            file_options={"content-type": "application/json", "upsert": "true"},
        )

    supabase_execute_with_retry(_do, "store_stats_snapshot")


def flush_table(supabase_client: Client) -> None:
    def _do() -> None:
        supabase_client.table(LISTINGS_TABLE).delete().neq("id", DELETE_SENTINEL_ID).execute()

    supabase_execute_with_retry(_do, "flush_table")


def store_listing(supabase_client: Client, item: Dict[str, object]) -> None:
    def _do() -> None:
        supabase_client.table(LISTINGS_TABLE).insert(item).execute()

    supabase_execute_with_retry(_do, "store_listing")


def supabase_execute_with_retry(fn, desc: str, retries: int = 3, base_sleep_s: float = 2.0) -> None:
    last_exc: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            fn()
            return
        except Exception as exc:  # noqa: BLE001 - we need broad protection for transient network errors
            last_exc = exc
            sleep_s = base_sleep_s * attempt
            logger.warning("Supabase %s failed (attempt %d/%d): %s", desc, attempt, retries, exc)
            if attempt < retries:
                time.sleep(sleep_s)
    if last_exc:
        raise last_exc


async def run_scraper(
    headless: bool,
    dry_run: bool,
    use_ai_matching: bool,
    shop_names: Optional[List[str]] = None,
) -> None:
    global EUR_TO_HUF_RATE
    EUR_TO_HUF_RATE = get_eur_to_huf_rate()

    supabase_client, ai_client = get_clients(use_ai_matching=use_ai_matching)
    shop_configs = get_shop_configs()
    if shop_names:
        allowed = {s.strip().lower() for s in shop_names if s and s.strip()}
        shop_configs = [cfg for cfg in shop_configs if cfg.name.strip().lower() in allowed]
        if not shop_configs:
            logger.warning("No shops matched --shops=%s", shop_names)
    shop_counts: Dict[str, int] = {}

    async with async_playwright() as p:
        browser: Browser = await p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=REQUEST_HEADERS["User-Agent"],
            locale="hu-HU",
            timezone_id="Europe/Budapest",
            viewport={"width": 1440, "height": 900},
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )
        page = await context.new_page()

        all_data: List[Dict[str, object]] = []
        for config in shop_configs:
            rows = await scrape_shop(page, config)
            shop_counts[config.name] = len(rows)
            all_data.extend(rows)
        await context.close()
        await browser.close()

    if not all_data:
        logger.info("No in-stock products found.")
        send_alert(
            "No in-stock products found in scraper run",
            {"shop_counts": shop_counts, "headless": headless, "dry_run": dry_run},
        )
        return

    logger.info("Found %d in-stock products, running HU shop comparison mode.", len(all_data))
    zero_shops = [shop for shop, count in shop_counts.items() if count == 0]
    if zero_shops:
        send_alert(
            "One or more shops returned 0 products",
            {"shops": zero_shops, "shop_counts": shop_counts},
        )
    if len(all_data) < MIN_EXPECTED_PRODUCTS:
        send_alert(
            "Scraped product count below expected threshold",
            {"count": len(all_data), "min_expected": MIN_EXPECTED_PRODUCTS, "shop_counts": shop_counts},
        )

    if not dry_run:
        flush_table(supabase_client)

    staged_items: List[Dict[str, object]] = []
    ai_match_cache: Dict[str, Tuple[bool, Optional[str]]] = {}

    for item in all_data:
        original_title = str(item.get("raw_title", "")).strip()
        if use_ai_matching and ai_client and original_title:
            if original_title in ai_match_cache:
                is_valid, canonical_title = ai_match_cache[original_title]
            else:
                is_valid, canonical_title = ai_canonicalize_title(ai_client, original_title)
                ai_match_cache[original_title] = (is_valid, canonical_title)
            if not is_valid or not canonical_title:
                continue
            item["raw_title"] = canonical_title
        else:
            item["raw_title"] = original_title

        item["demand_score"] = int(item.get("demand_score", 50) or 50)
        item["cm30"] = None
        item["cm7"] = None

        staged_items.append(item)

    # Keep one best offer per shop + normalized title to reduce duplicates/noise.
    deduped_by_shop_title: Dict[Tuple[str, str], Dict[str, object]] = {}
    for item in staged_items:
        key = (str(item.get("shop_name", "")), str(item.get("raw_title", "")).strip().lower())
        existing = deduped_by_shop_title.get(key)
        if not existing:
            deduped_by_shop_title[key] = item
            continue
        existing_price = int(existing.get("price_huf", 0) or 0)
        new_price = int(item.get("price_huf", 0) or 0)
        if existing_price <= 0 or (new_price > 0 and new_price < existing_price):
            deduped_by_shop_title[key] = item

    final_items = list(deduped_by_shop_title.values())
    logger.info("Post-processing: %d -> %d records after dedupe.", len(staged_items), len(final_items))

    if not dry_run and use_ai_matching and ai_client and final_items:
        try:
            from market_trends import refresh_market_trends, trend_score_map

            catalog_titles = [str(item.get("raw_title", "")).strip() for item in final_items]
            trends = refresh_market_trends(supabase_client, ai_client, catalog_titles)
            scores = trend_score_map(trends)
            for item in final_items:
                key = canonical_key_for_grouping(str(item.get("raw_title", "")))
                if key in scores:
                    item["demand_score"] = scores[key]
        except Exception as exc:
            logger.warning("Market trends refresh failed: %s", exc)

    if dry_run:
        logger.info("Finished dry-run with %d processed records.", len(final_items))
        return

    inserted = 0
    for item in final_items:
        try:
            store_listing(supabase_client, item)
            inserted += 1
        except Exception as exc:
            logger.warning("DB insert failed for %s: %s", item.get("raw_title"), exc)

    logger.info("Finished. Inserted %d/%d records.", inserted, len(final_items))
    if inserted > 0:
        try:
            stats = compute_run_stats(final_items)
            store_stats_snapshot(supabase_client, stats)
            logger.info(
                "Saved stats snapshot: %d products, %d shops, %d offers.",
                stats["in_stock_products"],
                stats["shops_count"],
                stats["in_stock_offers"],
            )
        except Exception as exc:
            logger.warning("Could not save stats snapshot: %s", exc)
    if inserted == 0:
        send_alert("Scraper finished with 0 inserted records", {"final_items": len(final_items), "shop_counts": shop_counts})
    elif inserted < len(final_items):
        send_alert(
            "Scraper partially inserted records",
            {"inserted": inserted, "final_items": len(final_items), "shop_counts": shop_counts},
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape Pokemon products for HU shop comparison.")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode.")
    parser.add_argument("--dry-run", action="store_true", help="Skip Supabase delete/insert operations.")
    parser.add_argument("--check", action="store_true", help="Validate required environment variables and exit.")
    parser.add_argument("--no-ai-matching", action="store_true", help="Disable OpenAI-based product matching.")
    parser.add_argument(
        "--shops",
        type=str,
        default="",
        help="Comma-separated shop names to scrape (exact match to ShopConfig.name).",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    use_ai_matching = not args.no_ai_matching
    if args.check:
        missing_vars = validate_required_env_vars(use_ai_matching=use_ai_matching)
        if missing_vars:
            logger.error("Missing required environment variables: %s", ", ".join(missing_vars))
            raise SystemExit(1)
        logger.info("Environment check passed. All required variables are present.")
        return
    shop_names = [s.strip() for s in args.shops.split(",") if s.strip()] if args.shops else None
    await run_scraper(
        headless=args.headless,
        dry_run=args.dry_run,
        use_ai_matching=use_ai_matching,
        shop_names=shop_names,
    )


if __name__ == "__main__":
    asyncio.run(main())