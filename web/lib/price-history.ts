import type { SupabaseClient } from "@supabase/supabase-js";

const STATS_BUCKET = "pokedeals-meta";
const HISTORY_OBJECT = "product_price_history.json";

export type PriceHistoryPoint = {
  recordedAt: string;
  lowestHuf: number;
  medianHuf: number;
  offerCount: number;
};

type HistoryPayload = {
  products?: Record<
    string,
    {
      points?: Array<{
        recorded_at?: string;
        lowest_huf?: number;
        median_huf?: number;
        offer_count?: number;
      }>;
    }
  >;
};

export async function loadProductPriceHistory(
  supabase: SupabaseClient,
  productSlug: string,
): Promise<PriceHistoryPoint[]> {
  const { data, error } = await supabase.storage.from(STATS_BUCKET).download(HISTORY_OBJECT);
  if (error || !data) return [];

  try {
    const payload = JSON.parse(await data.text()) as HistoryPayload;
    const productKey = productSlug.replace(/-/g, " ");
    const entry =
      payload.products?.[productSlug] ??
      payload.products?.[productKey] ??
      Object.entries(payload.products ?? {}).find(([key]) =>
        key.replace(/\s+/g, "-") === productSlug,
      )?.[1];

    const points = entry?.points ?? [];
    return points
      .map((point) => ({
        recordedAt: String(point.recorded_at ?? ""),
        lowestHuf: Number(point.lowest_huf) || 0,
        medianHuf: Number(point.median_huf) || 0,
        offerCount: Number(point.offer_count) || 0,
      }))
      .filter((point) => point.recordedAt && point.lowestHuf > 0)
      .sort((a, b) => a.recordedAt.localeCompare(b.recordedAt));
  } catch {
    return [];
  }
}

export function priceChangeSincePrevious(points: PriceHistoryPoint[]): number | null {
  if (points.length < 2) return null;
  const prev = points[points.length - 2].lowestHuf;
  const latest = points[points.length - 1].lowestHuf;
  if (prev <= 0 || latest <= 0) return null;
  return Math.round(((latest - prev) / prev) * 100);
}
