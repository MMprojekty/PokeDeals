import { NextResponse } from "next/server";
import { fetchComparisonProducts, type ComparisonProduct } from "@/lib/listings";

const CACHE_CONTROL = "public, s-maxage=120, stale-while-revalidate=300";

export const revalidate = 120;

function toClientProduct(product: ComparisonProduct) {
  return {
    displayTitle: product.displayTitle,
    lowestPrice: product.lowestPrice,
    highestPrice: product.highestPrice,
    medianPrice: product.medianPrice,
    spread: product.spread,
    bestVsMedian: product.bestVsMedian,
    score: product.score,
    imageUrl: product.imageUrl,
    hasStock: true,
    offers: product.offers.map((offer) => ({
      shop_name: offer.shopName,
      price_huf: offer.priceHuf,
      product_url: offer.productUrl,
      raw_title: offer.rawTitle,
      image_url: offer.imageUrl,
    })),
  };
}

export async function GET() {
  try {
    const result = await fetchComparisonProducts();
    return NextResponse.json(
      {
        data: result.products.map(toClientProduct),
        meta: {
          totalOffers: result.totalOffers,
          shopCount: result.shopCount,
          inStockProducts: result.inStockProducts,
          lastUpdated: result.lastUpdated,
          schema: result.schema,
          deltas: result.deltas,
        },
      },
      { status: 200, headers: { "Cache-Control": CACHE_CONTROL } },
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json(
      { error: message },
      { status: 500, headers: { "Cache-Control": "no-store" } },
    );
  }
}
