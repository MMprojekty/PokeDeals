import type { SupabaseClient } from "@supabase/supabase-js";

const STATS_BUCKET = "pokedeals-meta";
const MARKET_TRENDS_OBJECT = "market_trends.json";

function canonicalKey(name: string): string {
  return name
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/pokemon\s*tcg[:\-\s]*/g, " ")
    .replace(/pokemon[:\-\s]*/g, " ")
    .replace(/[^a-z0-9]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export type MarketTrendEntry = {
  canonical_title: string;
  demand_score: number;
  signal?: string;
};

export type MarketTrendsPayload = {
  updated_at: string | null;
  ranked: MarketTrendEntry[];
  market_note?: string;
};

export function buildTrendScoreMap(payload: MarketTrendsPayload | null): Map<string, number> {
  const map = new Map<string, number>();
  if (!payload?.ranked?.length) return map;

  for (const entry of payload.ranked) {
    const title = String(entry.canonical_title || "").trim();
    if (!title) continue;
    const score = Number(entry.demand_score);
    map.set(canonicalKey(title), Number.isFinite(score) ? Math.max(0, Math.min(100, score)) : 50);
  }
  return map;
}

export async function loadMarketTrends(
  supabase: SupabaseClient,
): Promise<MarketTrendsPayload | null> {
  const { data, error } = await supabase.storage.from(STATS_BUCKET).download(MARKET_TRENDS_OBJECT);
  if (error || !data) return null;

  try {
    const payload = JSON.parse(await data.text()) as MarketTrendsPayload;
    if (!payload || !Array.isArray(payload.ranked)) return null;
    return payload;
  } catch {
    return null;
  }
}

export function trendScoreForTitle(title: string, trendMap: Map<string, number>): number {
  return trendMap.get(canonicalKey(title)) ?? 50;
}
