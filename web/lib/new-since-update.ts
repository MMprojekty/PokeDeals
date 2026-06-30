import type { SupabaseClient } from "@supabase/supabase-js";

const STATS_BUCKET = "pokedeals-meta";
const NEW_SINCE_UPDATE_OBJECT = "new_since_update.json";

export type NewSinceUpdatePayload = {
  updated_at?: string;
  product_keys?: string[];
  offer_product_keys?: string[];
};

export async function loadNewSinceUpdate(
  supabase: SupabaseClient,
): Promise<NewSinceUpdatePayload | null> {
  const { data, error } = await supabase.storage.from(STATS_BUCKET).download(NEW_SINCE_UPDATE_OBJECT);
  if (error || !data) return null;

  try {
    const payload = JSON.parse(await data.text()) as NewSinceUpdatePayload;
    if (!payload || typeof payload !== "object") return null;
    return payload;
  } catch {
    return null;
  }
}
