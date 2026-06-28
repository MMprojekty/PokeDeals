import { NextResponse } from "next/server";
import { fetchComparisonProducts } from "@/lib/listings";
import { toClientProduct } from "@/lib/listings-client";

const CACHE_CONTROL = "public, s-maxage=120, stale-while-revalidate=300";

export const revalidate = 120;

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
          marketNote: result.marketNote,
          trendsUpdatedAt: result.trendsUpdatedAt,
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
