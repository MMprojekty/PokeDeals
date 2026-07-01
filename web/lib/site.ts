import { routing } from "@/i18n/routing";

const FALLBACK_SITE_URL = "https://pokedeals.vercel.app";

export function getSiteUrl(): string {
  const raw = process.env.NEXT_PUBLIC_SITE_URL?.trim();
  if (!raw) return FALLBACK_SITE_URL;
  return raw.replace(/\/+$/, "");
}

export function localePath(locale: string, path = ""): string {
  const normalized = path.startsWith("/") ? path : path ? `/${path}` : "";
  if (locale === routing.defaultLocale) {
    return normalized || "/";
  }
  return `/${locale}${normalized}`;
}

export function absoluteUrl(locale: string, path = ""): string {
  return `${getSiteUrl()}${localePath(locale, path)}`;
}
