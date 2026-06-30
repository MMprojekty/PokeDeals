import type { MetadataRoute } from "next";
import { fetchComparisonProducts } from "@/lib/listings";
import { absoluteUrl } from "@/lib/site";
import { routing } from "@/i18n/routing";

const PUBLIC_PATHS = ["", "/terms", "/privacy"] as const;

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const now = new Date();
  const staticEntries = routing.locales.flatMap((locale) =>
    PUBLIC_PATHS.map((path) => ({
      url: absoluteUrl(locale, path),
      lastModified: now,
      changeFrequency: path === "" ? ("hourly" as const) : ("monthly" as const),
      priority: path === "" ? 1 : 0.4,
    })),
  );

  let productEntries: MetadataRoute.Sitemap = [];
  if (process.env.GITHUB_PAGES !== "true") {
    try {
      const result = await fetchComparisonProducts();
      productEntries = routing.locales.flatMap((locale) =>
        result.products.map((product) => ({
          url: absoluteUrl(locale, `/product/${product.slug}`),
          lastModified: result.lastUpdated ? new Date(result.lastUpdated) : now,
          changeFrequency: "hourly" as const,
          priority: 0.8,
        })),
      );
    } catch {
      productEntries = [];
    }
  }

  return [...staticEntries, ...productEntries];
}
