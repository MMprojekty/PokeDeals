import type { MetadataRoute } from "next";
import { absoluteUrl } from "@/lib/site";
import { routing } from "@/i18n/routing";

const PUBLIC_PATHS = ["", "/terms", "/privacy"] as const;

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();

  return routing.locales.flatMap((locale) =>
    PUBLIC_PATHS.map((path) => ({
      url: absoluteUrl(locale, path),
      lastModified: now,
      changeFrequency: path === "" ? ("hourly" as const) : ("monthly" as const),
      priority: path === "" ? 1 : 0.4,
    })),
  );
}
