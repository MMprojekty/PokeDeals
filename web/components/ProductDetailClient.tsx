"use client";

import { useLocale, useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { TrackOutboundLink } from "@/components/TrackOutboundLink";
import type { PriceHistoryPoint } from "@/lib/price-history";
import { priceChangeSincePrevious } from "@/lib/price-history";

type ProductOffer = {
  shop_name: string;
  shop_slug: string;
  price_huf: number;
  product_url: string;
};

type ProductDetailClientProps = {
  product: {
    slug: string;
    displayTitle: string;
    lowestPrice: number;
    medianPrice: number;
    highestPrice: number;
    spread: number;
    bestVsMedian: number;
    trendingScore: number;
    imageUrl: string;
    offers: ProductOffer[];
  };
  locale: string;
  lastUpdated: string | null;
  priceHistory: PriceHistoryPoint[];
};

function formatPrice(locale: string, price: number, notAvailable: string) {
  if (!price || price === Infinity) return notAvailable;
  return new Intl.NumberFormat(locale === "hu" ? "hu-HU" : "en-GB").format(price) + " Ft";
}

function PriceSparkline({ points, locale }: { points: PriceHistoryPoint[]; locale: string }) {
  const t = useTranslations("product");
  if (points.length < 2) {
    return (
      <p className="text-xs text-gray-500">{t("historyPending")}</p>
    );
  }

  const values = points.map((point) => point.lowestHuf);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const change = priceChangeSincePrevious(points);

  return (
    <div className="space-y-3">
      <div className="flex items-end gap-1 h-16">
        {points.slice(-24).map((point, index) => {
          const height = ((point.lowestHuf - min) / range) * 100;
          return (
            <div
              key={`${point.recordedAt}-${index}`}
              title={`${new Date(point.recordedAt).toLocaleString(locale === "hu" ? "hu-HU" : "en-GB")}: ${formatPrice(locale, point.lowestHuf, "—")}`}
              className="flex-1 min-w-[3px] rounded-t bg-[#a63c5e]/70 hover:bg-[#a63c5e] transition-colors"
              style={{ height: `${Math.max(12, height)}%` }}
            />
          );
        })}
      </div>
      <div className="flex flex-wrap items-center gap-3 text-xs text-gray-600">
        <span>
          {t("historyLow")}: {formatPrice(locale, min, "—")}
        </span>
        <span>
          {t("historyHigh")}: {formatPrice(locale, max, "—")}
        </span>
        {change !== null ? (
          <span className={change < 0 ? "text-emerald-600 font-semibold" : change > 0 ? "text-rose-600 font-semibold" : ""}>
            {change > 0 ? "+" : ""}
            {change}% {t("sinceLastScrape")}
          </span>
        ) : null}
      </div>
    </div>
  );
}

export function ProductDetailClient({
  product,
  locale,
  lastUpdated,
  priceHistory,
}: ProductDetailClientProps) {
  const t = useTranslations();
  const activeLocale = useLocale();

  const format = (price: number) => formatPrice(activeLocale, price, t("common.notAvailable"));

  const updatedLabel = lastUpdated
    ? new Date(lastUpdated).toLocaleString(activeLocale === "hu" ? "hu-HU" : "en-GB", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      })
    : null;

  return (
    <main className="min-h-screen bg-[#f1f0ec] text-gray-900 font-sans p-6 md:p-10">
      <div className="max-w-6xl mx-auto">
        <div className="mb-10 flex items-center justify-between gap-4 flex-wrap">
          <Link href="/" className="flex items-center gap-2 rounded-lg transition-opacity hover:opacity-80">
            <div className="w-8 h-8 rounded-full bg-[#a63c5e] flex items-center justify-center text-white font-bold text-xl">
              P
            </div>
            <span className="text-2xl font-bold tracking-tight">{t("common.appName")}</span>
          </Link>
          {updatedLabel ? (
            <span className="text-xs font-semibold text-gray-500">
              {t("common.lastUpdated")}: {updatedLabel}
            </span>
          ) : null}
        </div>

        <Link
          href="/"
          className="text-[#4b3585] font-bold text-sm flex items-center gap-2 mb-6 hover:opacity-80 transition-opacity uppercase tracking-wider"
        >
          ← {t("home.back")}
        </Link>

        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden flex flex-col md:flex-row mb-6">
          <div className="bg-gray-50 p-10 md:w-1/2 flex items-center justify-center border-r border-gray-100">
            {product.imageUrl ? (
              <img
                src={product.imageUrl}
                alt={product.displayTitle}
                className="max-h-[400px] object-contain drop-shadow-xl"
              />
            ) : (
              <div className="w-full h-64 bg-gray-200 rounded flex items-center justify-center text-gray-400 font-bold">
                NO IMAGE
              </div>
            )}
          </div>

          <div className="p-8 md:p-12 md:w-1/2 flex flex-col">
            <h1 className="text-3xl font-extrabold text-gray-900 mb-4">{product.displayTitle}</h1>

            <div className="grid grid-cols-2 gap-3 mb-6">
              <div className="rounded-xl bg-emerald-50 border border-emerald-100 p-3">
                <div className="text-[10px] font-bold uppercase tracking-wider text-emerald-700">
                  {t("pricing.lowest")}
                </div>
                <div className="text-xl font-extrabold text-gray-900 mt-1">{format(product.lowestPrice)}</div>
              </div>
              <div className="rounded-xl bg-gray-50 border border-gray-100 p-3">
                <div className="text-[10px] font-bold uppercase tracking-wider text-gray-500">
                  {t("pricing.median")}
                </div>
                <div className="text-xl font-extrabold text-gray-900 mt-1">{format(product.medianPrice)}</div>
              </div>
            </div>

            <div className="flex items-center gap-4 mb-6 flex-wrap">
              <span className="text-xs font-bold text-[#4b3585] uppercase tracking-wider">
                {t("home.comparing")} {product.offers.length} {t("home.storeOffers")}
              </span>
              {product.trendingScore >= 75 ? (
                <span className="rounded-full bg-orange-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-orange-700">
                  🔥 {t("home.trendingBadge")}
                </span>
              ) : null}
              {product.bestVsMedian < 0 ? (
                <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-emerald-700">
                  {t("home.bestVsMedian")}
                </span>
              ) : null}
            </div>

            <div className="w-full h-px bg-gray-100 mb-6" />

            <div className="flex-1 overflow-y-auto space-y-4 pr-2">
              {product.offers.map((offer) => (
                <div
                  key={`${offer.shop_slug}-${offer.product_url}`}
                  className="flex justify-between items-center group bg-gray-50/80 border border-gray-100 rounded-xl px-4 py-3"
                >
                  <div>
                    <h2 className="font-bold text-lg text-gray-900 group-hover:text-[#a63c5e] transition-colors">
                      {offer.shop_name}
                    </h2>
                    <p className="text-[10px] font-bold text-green-500 uppercase tracking-wider mt-1 flex items-center gap-1">
                      <span className="w-2 h-2 rounded-full bg-green-500 block" />
                      {t("stock.inStock")}
                    </p>
                  </div>
                  <div className="text-right">
                    <div className="font-extrabold text-xl text-gray-900">{format(offer.price_huf)}</div>
                    <TrackOutboundLink
                      href={offer.product_url}
                      productSlug={product.slug}
                      shopSlug={offer.shop_slug}
                      priceHuf={offer.price_huf}
                      className="text-[11px] font-bold text-[#a63c5e] uppercase tracking-wider mt-1 block hover:underline"
                    >
                      {t("home.viewDeal")} →
                    </TrackOutboundLink>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <section className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 md:p-8">
          <h2 className="text-lg font-bold text-gray-900 mb-1">{t("product.priceHistory")}</h2>
          <p className="text-sm text-gray-500 mb-4">{t("product.priceHistoryHint")}</p>
          <PriceSparkline points={priceHistory} locale={locale} />
        </section>
      </div>
    </main>
  );
}
