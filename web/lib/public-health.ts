const STALE_AFTER_MINUTES = 45;

export type PublicHealthSnapshot = {
  badgeLevel: "green" | "amber" | "red";
  ageMinutes: number | null;
  latestScrapeAt: string | null;
  totalInStockRows: number;
  totalRows: number;
  stale: boolean;
};

function statusUrl(): string | null {
  const base = process.env.NEXT_PUBLIC_SUPABASE_URL?.replace(/\/+$/, "");
  if (!base) return null;
  return `${base}/storage/v1/object/public/pokedeals-public/status.json`;
}

export async function fetchPublicHealthSnapshot(): Promise<PublicHealthSnapshot | null> {
  const url = statusUrl();
  if (!url) return null;
  try {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) return null;
    const payload = await response.json();
    const latestScrapeAt =
      typeof payload.latestScrapeAt === "string" ? payload.latestScrapeAt : null;
    const ageMinutes =
      typeof payload.ageMinutes === "number"
        ? payload.ageMinutes
        : latestScrapeAt
          ? Math.floor((Date.now() - new Date(latestScrapeAt).getTime()) / 60000)
          : null;
    const stale = ageMinutes === null ? true : ageMinutes > STALE_AFTER_MINUTES;
    const totalRows = Number(payload.totalRows) || 0;
    const totalInStockRows = Number(payload.totalInStockRows) || 0;
    let badgeLevel: "green" | "amber" | "red" = "green";
    if (totalRows === 0) badgeLevel = "red";
    else if (totalInStockRows === 0 || stale) badgeLevel = "amber";

    return {
      badgeLevel,
      ageMinutes,
      latestScrapeAt,
      totalInStockRows,
      totalRows,
      stale,
    };
  } catch {
    return null;
  }
}
