import type { ComparisonProduct, ListingsFetchResult } from "@/lib/listings";

export type ClientShopOffer = {
  shop_name: string;
  shop_slug: string;
  price_huf: number;
  product_url: string;
  raw_title?: string;
  image_url?: string | null;
};

export type ClientComparisonRow = {
  slug: string;
  displayTitle: string;
  lowestPrice: number;
  highestPrice: number;
  medianPrice: number;
  spread: number;
  bestVsMedian: number;
  score: number;
  trendingScore: number;
  imageUrl: string;
  isNewSinceLastUpdate: boolean;
  hasNewOffersSinceLastUpdate: boolean;
  offers: ClientShopOffer[];
};

export type InitialListingsPayload = {
  products: ClientComparisonRow[];
  totalOffers: number;
  shopCount: number;
  statsDeltas: {
    inStockProducts: number | null;
    shops: number | null;
    inStockOffers: number | null;
  };
};

export function toClientProduct(product: ComparisonProduct): ClientComparisonRow {
  return {
    slug: product.slug,
    displayTitle: product.displayTitle,
    lowestPrice: product.lowestPrice,
    highestPrice: product.highestPrice,
    medianPrice: product.medianPrice,
    spread: product.spread,
    bestVsMedian: product.bestVsMedian,
    score: product.score,
    trendingScore: product.trendingScore,
    imageUrl: product.imageUrl,
    isNewSinceLastUpdate: product.isNewSinceLastUpdate,
    hasNewOffersSinceLastUpdate: product.hasNewOffersSinceLastUpdate,
    offers: product.offers.map((offer) => ({
      shop_name: offer.shopName,
      shop_slug: offer.shopSlug,
      price_huf: offer.priceHuf,
      product_url: offer.productUrl,
      raw_title: offer.rawTitle,
      image_url: offer.imageUrl,
    })),
  };
}

export function toClientPayload(result: ListingsFetchResult): InitialListingsPayload {
  return {
    products: result.products.map(toClientProduct),
    totalOffers: result.totalOffers,
    shopCount: result.shopCount,
    statsDeltas: result.deltas,
  };
}
