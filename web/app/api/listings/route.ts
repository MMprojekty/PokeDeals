import { NextResponse } from "next/server";
import { fetchComparisonProducts } from "@/lib/listings";
import { toClientProduct } from "@/lib/listings-client";

const CACHE_CONTROL = "no-store";

export const revalidate = 0;

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
