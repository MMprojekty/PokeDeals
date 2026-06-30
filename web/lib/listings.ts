import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { buildTrendScoreMap, loadMarketTrends } from "@/lib/market-trends";
import { loadNewSinceUpdate } from "@/lib/new-since-update";
import { findProductSlug, slugMatchesProduct } from "@/lib/product-slug";

/** One shop offer attached to a canonical product (comparison row). */
export type ShopOffer = {
  listingId: string;
  shopSlug: string;
  shopName: string;
  rawTitle: string;
  productUrl: string;
  priceHuf: number;
  stockStatus: string;
  imageUrl: string | null;
  scrapedAt: string | null;
};

/** Canonical product with grouped in-stock offers, ready for the UI. */
export type ComparisonProduct = {
  productId: string;
  slug: string;
  displayTitle: string;
  category: string | null;
  setName: string | null;
  imageUrl: string;
  lowestPrice: number;
  highestPrice: number;
  medianPrice: number;
  spread: number;
  bestVsMedian: number;
  score: number;
  trendingScore: number;
  isNewSinceLastUpdate: boolean;
  hasNewOffersSinceLastUpdate: boolean;
  offers: ShopOffer[];
};

type ListingRow = {
  product_id: string;
  canonical_name: string;
  canonical_slug: string;
  category: string | null;
  set_name: string | null;
  product_image_url: string | null;
  listing_id: string;
  shop_slug: string;
  shop_name: string;
  raw_title: string;
  product_url: string;
  price_huf: number;
  stock_status: string;
  listing_image_url: string | null;
  scraped_at: string | null;
  updated_at: string | null;
};

/** Legacy flat table shape (current production: shop_listings). */
type LegacyListingRow = {
  id?: string;
  shop_name: string;
  raw_title: string;
  price_huf: number;
  stock_status: string;
  product_url: string;
  image_url?: string | null;
  updated_at?: string | null;
  created_at?: string | null;
};

function median(values: number[]): number {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? Math.round((sorted[mid - 1] + sorted[mid]) / 2)
    : sorted[mid];
}

export function canonicalKey(name: string): string {
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

function formatDisplayTitle(title: string): string {
  return title
    .replace(/^[\s\-–—:]+/, "")
    .replace(/\s+/g, " ")
    .trim();
}

function buildComparisonProduct(
  productId: string,
  displayTitle: string,
  category: string | null,
  setName: string | null,
  imageUrl: string,
  offers: ShopOffer[],
  trendingScore = 50,
): ComparisonProduct {
  const validPrices = offers.map((o) => o.priceHuf).filter((p) => p > 0);
  const lowestPrice = validPrices.length ? Math.min(...validPrices) : 0;
  const highestPrice = validPrices.length ? Math.max(...validPrices) : 0;
  const medianPrice = median(validPrices);
  const spread = validPrices.length ? highestPrice - lowestPrice : 0;
  const bestVsMedian =
    medianPrice > 0 && lowestPrice > 0
      ? Math.round(((lowestPrice - medianPrice) / medianPrice) * 100)
      : 0;
  const score = trendingScore * 1000 + offers.length * 100 + Math.max(0, -bestVsMedian);

  return {
    productId,
    slug: findProductSlug(formatDisplayTitle(displayTitle), productId),
    displayTitle: formatDisplayTitle(displayTitle),
    category,
    setName,
    imageUrl,
    lowestPrice,
    highestPrice,
    medianPrice,
    spread,
    bestVsMedian,
    score,
    trendingScore,
    isNewSinceLastUpdate: false,
    hasNewOffersSinceLastUpdate: false,
    offers: [...offers].sort((a, b) => a.priceHuf - b.priceHuf),
  };
}

/** Normalized schema: products_with_listings view. */
export function groupNormalizedListings(rows: ListingRow[]): ComparisonProduct[] {
  const byProduct = new Map<string, ComparisonProduct>();

  for (const row of rows) {
    if (row.stock_status !== "in_stock") continue;

    const offer: ShopOffer = {
      listingId: row.listing_id,
      shopSlug: row.shop_slug,
      shopName: row.shop_name,
      rawTitle: row.raw_title,
      productUrl: row.product_url,
      priceHuf: row.price_huf,
      stockStatus: row.stock_status,
      imageUrl: row.listing_image_url,
      scrapedAt: row.scraped_at,
    };

    const existing = byProduct.get(row.product_id);
    if (!existing) {
      byProduct.set(
        row.product_id,
        buildComparisonProduct(
          row.product_id,
          row.canonical_name,
          row.category,
          row.set_name,
          row.product_image_url || row.listing_image_url || "",
          [offer],
        ),
      );
      continue;
    }

    existing.offers.push(offer);
    if (!existing.imageUrl && (row.listing_image_url || row.product_image_url)) {
      existing.imageUrl = row.product_image_url || row.listing_image_url || "";
    }
    const rebuilt = buildComparisonProduct(
      existing.productId,
      existing.displayTitle,
      existing.category,
      existing.setName,
      existing.imageUrl,
      existing.offers,
    );
    byProduct.set(row.product_id, rebuilt);
  }

  return [...byProduct.values()].sort((a, b) => b.score - a.score);
}

/** Legacy flat shop_listings table (current app behavior). */
export function groupLegacyListings(
  rows: LegacyListingRow[],
  trendScores: Map<string, number> = new Map(),
): ComparisonProduct[] {
  const grouped = new Map<string, ComparisonProduct>();

  for (const row of rows) {
    if (!String(row.stock_status || "").toUpperCase().includes("IN_STOCK")) continue;

    const key = canonicalKey(row.raw_title);
    const trendingScore = trendScores.get(key) ?? 50;
    const offer: ShopOffer = {
      listingId: row.id || `${row.shop_name}-${row.product_url}`,
      shopSlug: row.shop_name.toLowerCase().replace(/\s+/g, "-"),
      shopName: row.shop_name,
      rawTitle: row.raw_title,
      productUrl: row.product_url,
      priceHuf: row.price_huf,
      stockStatus: "in_stock",
      imageUrl: row.image_url ?? null,
      scrapedAt: row.updated_at ?? row.created_at ?? null,
    };

    const existing = grouped.get(key);
    if (!existing) {
      grouped.set(
        key,
        buildComparisonProduct(key, row.raw_title, null, null, row.image_url || "", [offer], trendingScore),
      );
      continue;
    }

    existing.offers.push(offer);
    if (!existing.imageUrl && row.image_url) existing.imageUrl = row.image_url;
    grouped.set(
      key,
      buildComparisonProduct(
        existing.productId,
        existing.displayTitle,
        existing.category,
        existing.setName,
        existing.imageUrl,
        existing.offers,
        Math.max(existing.trendingScore, trendingScore),
      ),
    );
  }

  return [...grouped.values()].sort((a, b) => b.score - a.score);
}

export type StatsDelta = {
  inStockProducts: number | null;
  shops: number | null;
  inStockOffers: number | null;
};

type StatsSnapshot = {
  in_stock_products: number;
  shops_count: number;
  in_stock_offers: number;
  product_keys?: string[];
  offer_keys?: string[];
};

function enrichWithNewFlags(
  products: ComparisonProduct[],
  previousSnapshot: StatsSnapshot | null,
  newSinceUpdate: { product_keys?: string[]; offer_product_keys?: string[] } | null,
): ComparisonProduct[] {
  const explicitNewProducts = new Set(newSinceUpdate?.product_keys ?? []);
  const explicitNewOffers = new Set(newSinceUpdate?.offer_product_keys ?? []);

  if (explicitNewProducts.size > 0 || explicitNewOffers.size > 0) {
    return products.map((product) => {
      const productKey = canonicalKey(product.displayTitle);
      return {
        ...product,
        isNewSinceLastUpdate:
          explicitNewProducts.has(productKey) || explicitNewProducts.has(product.productId),
        hasNewOffersSinceLastUpdate:
          explicitNewOffers.has(productKey) || explicitNewOffers.has(product.productId),
      };
    });
  }

  const prevProductKeys = new Set(previousSnapshot?.product_keys ?? []);
  const prevOfferKeys = new Set(previousSnapshot?.offer_keys ?? []);
  if (prevProductKeys.size === 0 && prevOfferKeys.size === 0) {
    return products;
  }

  return products.map((product) => {
    const productKey = canonicalKey(product.displayTitle);
    const isNewSinceLastUpdate =
      prevProductKeys.size > 0 &&
      !prevProductKeys.has(productKey) &&
      !prevProductKeys.has(product.productId);
    const hasNewOffersSinceLastUpdate =
      prevOfferKeys.size > 0 &&
      product.offers.some(
        (offer) => !prevOfferKeys.has(`${offer.shopName}|${productKey}`),
      );

    return {
      ...product,
      isNewSinceLastUpdate,
      hasNewOffersSinceLastUpdate,
    };
  });
}

function isInStockStatus(status: string | null | undefined): boolean {
  return String(status || "").toUpperCase().includes("IN_STOCK");
}

export function computeLegacyStats(
  rows: LegacyListingRow[],
  trendScores: Map<string, number> = new Map(),
) {
  const inStockRows = rows.filter((row) => isInStockStatus(row.stock_status));
  const products = groupLegacyListings(rows, trendScores);
  const shops = new Set(inStockRows.map((row) => row.shop_name).filter(Boolean));

  return {
    inStockProducts: products.length,
    shopCount: shops.size,
    inStockOffers: inStockRows.length,
  };
}

function deltaFromPrevious(current: number, previous: number | undefined): number | null {
  if (previous === undefined) return null;
  return current - previous;
}

async function fetchPreviousStatsSnapshot(supabase: SupabaseClient): Promise<StatsSnapshot | null> {
  const bucket = "pokedeals-meta";
  const objectPath = "stats_snapshots.json";

  const { data, error } = await supabase.storage.from(bucket).download(objectPath);
  if (error || !data) return null;

  try {
    const payload = JSON.parse(await data.text()) as {
      snapshots?: StatsSnapshot[];
    };
    const snapshots = payload.snapshots ?? [];
    if (snapshots.length === 0) return null;
    if (snapshots.length === 1) return snapshots[0];
    return snapshots[snapshots.length - 2];
  } catch {
    return null;
  }
}

export type ListingsFetchResult = {
  products: ComparisonProduct[];
  totalOffers: number;
  shopCount: number;
  inStockProducts: number;
  lastUpdated: string | null;
  schema: "normalized" | "legacy";
  deltas: StatsDelta;
  marketNote: string | null;
  trendsUpdatedAt: string | null;
};

/**
 * Server-side fetch for API routes.
 * Set USE_NORMALIZED_SCHEMA=true once migration is complete.
 */
export async function fetchComparisonProducts(): Promise<ListingsFetchResult> {
  const supabaseUrl = process.env.SUPABASE_URL;
  const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!supabaseUrl || !serviceRoleKey) {
    throw new Error("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY");
  }

  const useNormalized = process.env.USE_NORMALIZED_SCHEMA === "true";
  const supabase = createClient(supabaseUrl, serviceRoleKey);

  if (useNormalized) {
    const { data, error } = await supabase
      .from("products_with_listings")
      .select("*")
      .order("updated_at", { ascending: false });

    if (error) throw new Error(error.message);

    const rows = (data ?? []) as ListingRow[];
    const previousSnapshot = await fetchPreviousStatsSnapshot(supabase);
    const newSinceUpdate = await loadNewSinceUpdate(supabase);
    const products = enrichWithNewFlags(
      groupNormalizedListings(rows),
      previousSnapshot,
      newSinceUpdate,
    );
    const inStockRows = rows.filter((row) => row.stock_status === "in_stock");
    const shops = new Set(inStockRows.map((row) => row.shop_name));
    const lastUpdated =
      rows.map((r) => r.updated_at).filter(Boolean).sort().slice(-1)[0] ?? null;
    const currentStats = {
      inStockProducts: products.length,
      shopCount: shops.size,
      inStockOffers: inStockRows.length,
    };

    return {
      products,
      totalOffers: currentStats.inStockOffers,
      shopCount: currentStats.shopCount,
      inStockProducts: currentStats.inStockProducts,
      lastUpdated,
      schema: "normalized",
      marketNote: null,
      trendsUpdatedAt: null,
      deltas: {
        inStockProducts: deltaFromPrevious(
          currentStats.inStockProducts,
          previousSnapshot?.in_stock_products,
        ),
        shops: deltaFromPrevious(currentStats.shopCount, previousSnapshot?.shops_count),
        inStockOffers: deltaFromPrevious(
          currentStats.inStockOffers,
          previousSnapshot?.in_stock_offers,
        ),
      },
    };
  }

  const listingsTable = process.env.SUPABASE_LISTINGS_TABLE || "shop_listings";
  const { data, error } = await supabase
    .from(listingsTable)
    .select("*")
    .order("updated_at", { ascending: false });

  if (error) throw new Error(error.message);

  const rows = (data ?? []) as LegacyListingRow[];
  const [marketTrends, previousSnapshot, newSinceUpdate] = await Promise.all([
    loadMarketTrends(supabase),
    fetchPreviousStatsSnapshot(supabase),
    loadNewSinceUpdate(supabase),
  ]);
  const trendScores = buildTrendScoreMap(marketTrends);
  const products = enrichWithNewFlags(
    groupLegacyListings(rows, trendScores),
    previousSnapshot,
    newSinceUpdate,
  );
  const stats = computeLegacyStats(rows, trendScores);
  const lastUpdated =
    rows.map((r) => r.updated_at || r.created_at).filter(Boolean).sort().slice(-1)[0] ?? null;

  return {
    products,
    totalOffers: stats.inStockOffers,
    shopCount: stats.shopCount,
    inStockProducts: stats.inStockProducts,
    lastUpdated,
    schema: "legacy",
    marketNote: marketTrends?.market_note ?? null,
    trendsUpdatedAt: marketTrends?.updated_at ?? null,
    deltas: {
      inStockProducts: deltaFromPrevious(
        stats.inStockProducts,
        previousSnapshot?.in_stock_products,
      ),
      shops: deltaFromPrevious(stats.shopCount, previousSnapshot?.shops_count),
      inStockOffers: deltaFromPrevious(stats.inStockOffers, previousSnapshot?.in_stock_offers),
    },
  };
}

export async function fetchProductBySlug(slug: string): Promise<{
  product: ComparisonProduct;
  lastUpdated: string | null;
} | null> {
  const result = await fetchComparisonProducts();
  const product = result.products.find((entry) =>
    slugMatchesProduct(entry.displayTitle, slug, entry.productId),
  );
  if (!product) return null;
  return { product, lastUpdated: result.lastUpdated };
}
