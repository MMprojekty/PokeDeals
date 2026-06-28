import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { absoluteUrl } from "@/lib/site";

export async function buildHomeMetadata(locale: string): Promise<Metadata> {
  const t = await getTranslations({ locale, namespace: "seo" });
  const title = t("metaTitle");
  const description = t("metaDescription");
  const url = absoluteUrl(locale);

  return {
    title,
    description,
    keywords: t("keywords").split(",").map((word) => word.trim()),
    alternates: {
      canonical: url,
      languages: {
        en: absoluteUrl("en"),
        hu: absoluteUrl("hu"),
        "x-default": absoluteUrl("en"),
      },
    },
    openGraph: {
      type: "website",
      locale: locale === "hu" ? "hu_HU" : "en_GB",
      url,
      siteName: "PokéDeals",
      title,
      description,
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
    },
    robots: {
      index: true,
      follow: true,
      googleBot: {
        index: true,
        follow: true,
      },
    },
  };
}

export async function buildLegalMetadata(
  locale: string,
  page: "terms" | "privacy",
): Promise<Metadata> {
  const tNav = await getTranslations({ locale, namespace: "nav" });
  const tSeo = await getTranslations({ locale, namespace: "seo" });
  const label = page === "terms" ? tNav("terms") : tNav("privacy");
  const title = `${label} — PokéDeals`;
  const description =
    page === "terms" ? tSeo("termsDescription") : tSeo("privacyDescription");
  const path = page === "terms" ? "/terms" : "/privacy";

  return {
    title,
    description,
    alternates: {
      canonical: absoluteUrl(locale, path),
      languages: {
        en: absoluteUrl("en", path),
        hu: absoluteUrl("hu", path),
        "x-default": absoluteUrl("en", path),
      },
    },
    openGraph: {
      type: "article",
      url: absoluteUrl(locale, path),
      title,
      description,
    },
  };
}
