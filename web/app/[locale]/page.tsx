import { HomeClient } from "./HomeClient";
import { SeoJsonLd } from "@/components/SeoJsonLd";
import { fetchComparisonProducts } from "@/lib/listings";
import { toClientPayload } from "@/lib/listings-client";
import { buildHomeMetadata } from "@/lib/seo";
import { setRequestLocale } from "next-intl/server";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  return buildHomeMetadata(locale);
}

export default async function HomePage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);

  let initialData = null;
  try {
    const result = await fetchComparisonProducts();
    initialData = toClientPayload(result);
  } catch {
    initialData = null;
  }

  return (
    <>
      <SeoJsonLd locale={locale} products={initialData?.products ?? []} />
      <HomeClient initialData={initialData} />
    </>
  );
}
