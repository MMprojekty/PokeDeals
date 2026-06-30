import { notFound } from "next/navigation";
import { createClient } from "@supabase/supabase-js";
import { ProductDetail } from "@/components/ProductDetail";
import { ProductJsonLd } from "@/components/ProductJsonLd";
import { fetchProductBySlug } from "@/lib/listings";
import { loadProductPriceHistory, type PriceHistoryPoint } from "@/lib/price-history";
import { buildProductMetadata } from "@/lib/seo";
import { setRequestLocale } from "next-intl/server";

export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string; slug: string }>;
}) {
  const { locale, slug } = await params;
  const result = await fetchProductBySlug(slug).catch(() => null);
  if (!result) {
    return { title: "Product — PokéDeals" };
  }
  return buildProductMetadata(locale, result.product);
}

export default async function ProductPage({
  params,
}: {
  params: Promise<{ locale: string; slug: string }>;
}) {
  const { locale, slug } = await params;
  setRequestLocale(locale);

  const result = await fetchProductBySlug(slug).catch(() => null);
  if (!result) {
    notFound();
  }

  let priceHistory: PriceHistoryPoint[] = [];
  const supabaseUrl = process.env.SUPABASE_URL;
  const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (supabaseUrl && serviceRoleKey) {
    const supabase = createClient(supabaseUrl, serviceRoleKey);
    priceHistory = await loadProductPriceHistory(supabase, result.product.slug);
  }

  return (
    <>
      <ProductJsonLd locale={locale} product={result.product} />
      <ProductDetail
        product={result.product}
        locale={locale}
        lastUpdated={result.lastUpdated}
        priceHistory={priceHistory}
      />
    </>
  );
}
