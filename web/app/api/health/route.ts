import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.SUPABASE_URL;
const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
const listingsTable = process.env.SUPABASE_LISTINGS_TABLE || "shop_listings";
const CACHE_CONTROL = "no-store";
// Hourly scraper — treat data as fresh until ~90 min old (next run + buffer).
const STALE_AFTER_MINUTES = Number(process.env.SCRAPE_STALE_MINUTES || 90);

export const revalidate = 0;

export async function GET() {
  if (!supabaseUrl || !serviceRoleKey) {
    return NextResponse.json(
      { status: "error", error: "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in web environment." },
      { status: 500, headers: { "Cache-Control": "no-store" } },
    );
  }

  const supabase = createClient(supabaseUrl, serviceRoleKey);
  const { data, error } = await supabase
    .from(listingsTable)
    .select("shop_name, stock_status, updated_at");

  if (error) {
    return NextResponse.json(
      { status: "error", error: error.message },
      { status: 500, headers: { "Cache-Control": "no-store" } },
    );
  }

  const rows = data ?? [];
  const shopCounts: Record<string, number> = {};
  let inStockRows = 0;
  let latestEpoch = 0;

  for (const row of rows) {
    const shopName = String(row.shop_name || "unknown");
    const status = String(row.stock_status || "").toUpperCase();
    if (status.includes("IN_STOCK")) {
      inStockRows += 1;
      shopCounts[shopName] = (shopCounts[shopName] ?? 0) + 1;
    }
    const ts = row.updated_at;
    const epoch = ts ? new Date(ts).getTime() : 0;
    if (Number.isFinite(epoch) && epoch > latestEpoch) {
      latestEpoch = epoch;
    }
  }

  const latestScrapeAt = latestEpoch > 0 ? new Date(latestEpoch).toISOString() : null;
  const ageMinutes = latestEpoch > 0 ? Math.floor((Date.now() - latestEpoch) / 60000) : null;
  const stale = ageMinutes === null ? true : ageMinutes > STALE_AFTER_MINUTES;
  const zeroShops = Object.entries(shopCounts)
    .filter(([, count]) => count === 0)
    .map(([name]) => name);

  let badgeLevel: "green" | "amber" | "red" = "green";
  if (rows.length === 0) {
    badgeLevel = "red";
  } else if (inStockRows === 0 || stale) {
    badgeLevel = "amber";
  }

  return NextResponse.json(
    {
      status: stale ? "stale" : "ok",
      badgeLevel,
      totalRows: rows.length,
      totalInStockRows: inStockRows,
      latestScrapeAt,
      ageMinutes,
      stale,
      zeroShops,
      shopCounts,
    },
    { status: 200, headers: { "Cache-Control": CACHE_CONTROL } },
  );
}
