import { Suspense } from "react";
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
  if (process.env.GITHUB_PAGES !== "true") {
    try {
      const result = await fetchComparisonProducts();
      initialData = toClientPayload(result);
    } catch {
      initialData = null;
    }
  }

  return (
    <>
      <SeoJsonLd locale={locale} products={initialData?.products ?? []} />
      <Suspense
        fallback={
          <main className="min-h-screen bg-[#f1f0ec] p-10 text-center text-gray-600 font-semibold">
            Loading…
          </main>
        }
      >
        <HomeClient initialData={initialData} />
      </Suspense>
    </>
  );
}
