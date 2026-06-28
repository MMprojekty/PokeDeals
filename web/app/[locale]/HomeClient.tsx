"use client";

import { useEffect, useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { usePathname, useRouter, Link } from "@/i18n/navigation";
import type { ClientComparisonRow, InitialListingsPayload } from "@/lib/listings-client";

type ShopOffer = ClientComparisonRow["offers"][number];
type ComparisonRow = ClientComparisonRow;

type SortColumn = "score" | "product" | "lowestPrice" | "medianPrice" | "spread" | "bestVsMedian" | "offers";
type SortDirection = "asc" | "desc";

function SortIndicator({ active, direction }: { active: boolean; direction: SortDirection }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center text-sm leading-none ${
        active ? "text-[#a63c5e] font-black" : "text-gray-500 font-semibold"
      }`}
      aria-hidden
    >
      {active ? (direction === "asc" ? "▲" : "▼") : "⇅"}
    </span>
  );
}

function HeaderInfoIcon({ title }: { title: string }) {
  return (
    <span
      className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-gray-300 text-[9px] font-bold leading-none text-gray-400"
      title={title}
      onClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => e.stopPropagation()}
    >
      i
    </span>
  );
}

function StatDelta({ delta, label }: { delta: number | null; label: string }) {
  if (delta === null) return null;

  const unchanged = delta === 0;
  const positive = delta > 0;
  const sign = positive ? "+" : "";
  const colorClass = unchanged ? "text-gray-500" : positive ? "text-emerald-600" : "text-rose-600";

  return (
    <div className={`text-xs font-semibold mt-1 ${colorClass}`}>
      {unchanged ? "±0" : `${sign}${delta}`} {label}
    </div>
  );
}

function AppBrand({ onNavigateHome }: { onNavigateHome?: () => void }) {
  const t = useTranslations();
  const content = (
    <>
      <div className="w-8 h-8 rounded-full bg-[#a63c5e] flex items-center justify-center text-white font-bold text-xl">
        P
      </div>
      <span className="text-2xl font-bold tracking-tight">{t("common.appName")}</span>
    </>
  );
  const className = "flex items-center gap-2 rounded-lg transition-opacity hover:opacity-80";

  if (onNavigateHome) {
    return (
      <button type="button" onClick={onNavigateHome} className={className} aria-label={t("nav.home")}>
        {content}
      </button>
    );
  }

  return (
    <Link href="/" className={className} aria-label={t("nav.home")}>
      {content}
    </Link>
  );
}

export function HomeClient({ initialData }: { initialData?: InitialListingsPayload | null }) {
  const t = useTranslations();
  const locale = useLocale();
  const router = useRouter();
  const pathname = usePathname();

  const [products, setProducts] = useState<ComparisonRow[]>(initialData?.products ?? []);
  const [activeFilter, setActiveFilter] = useState("all");
  const [languageFilter, setLanguageFilter] = useState<"all" | "english">("all");
  const [totalOffers, setTotalOffers] = useState(initialData?.totalOffers ?? 0);
  const [shopsCount, setShopsCount] = useState(initialData?.shopCount ?? 0);
  const [statsDeltas, setStatsDeltas] = useState<{
    inStockProducts: number | null;
    shops: number | null;
    inStockOffers: number | null;
  }>(initialData?.statsDeltas ?? { inStockProducts: null, shops: null, inStockOffers: null });
  const [listingsLoading, setListingsLoading] = useState(!initialData);
  const [listingsError, setListingsError] = useState<string | null>(null);
  const [marketNote, setMarketNote] = useState<string | null>(null);
  const [healthInfo, setHealthInfo] = useState<{
    badgeLevel: "green" | "amber" | "red";
    ageMinutes: number | null;
    latestScrapeAt: string | null;
    totalInStockRows: number;
    totalRows: number;
    stale: boolean;
  } | null>(null);
  const [healthFetchFailed, setHealthFetchFailed] = useState(false);
  const [selectedProduct, setSelectedProduct] = useState<ComparisonRow | null>(null);
  const [sortColumn, setSortColumn] = useState<SortColumn>("score");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");

  function toggleSort(column: SortColumn) {
    if (sortColumn === column) {
      setSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setSortColumn(column);
    setSortDirection(column === "product" ? "asc" : "desc");
  }

  async function fetchHealthSnapshot() {
    try {
      const response = await fetch("/api/health", { cache: "no-store" });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        setHealthFetchFailed(true);
        setHealthInfo(null);
        return;
      }
      setHealthFetchFailed(false);
      const badgeLevel = (payload?.badgeLevel as "green" | "amber" | "red") || "amber";
      setHealthInfo({
        badgeLevel,
        ageMinutes: typeof payload.ageMinutes === "number" ? payload.ageMinutes : null,
        latestScrapeAt: typeof payload.latestScrapeAt === "string" ? payload.latestScrapeAt : null,
        totalInStockRows: Number(payload.totalInStockRows) || 0,
        totalRows: Number(payload.totalRows) || 0,
        stale: Boolean(payload.stale),
      });
    } catch {
      setHealthFetchFailed(true);
      setHealthInfo(null);
    }
  }

  async function fetchAndGroupData() {
    setListingsLoading(true);
    setListingsError(null);
    try {
      const response = await fetch("/api/listings", { cache: "no-store" });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        console.error("Error fetching data:", response.statusText);
        setListingsError(t("home.listingsLoadError"));
        setProducts([]);
        setTotalOffers(0);
        setShopsCount(0);
        setStatsDeltas({ inStockProducts: null, shops: null, inStockOffers: null });
        return;
      }

      const data = payload?.data;
      if (!Array.isArray(data)) {
        console.error("Error fetching data: invalid response payload");
        setListingsError(t("home.listingsLoadError"));
        setProducts([]);
        return;
      }

      setProducts(data);
      setTotalOffers(Number(payload?.meta?.totalOffers) || data.length);
      setShopsCount(Number(payload?.meta?.shopCount) || 0);
      const deltas = payload?.meta?.deltas;
      setStatsDeltas({
        inStockProducts:
          typeof deltas?.inStockProducts === "number" ? deltas.inStockProducts : null,
        shops: typeof deltas?.shops === "number" ? deltas.shops : null,
        inStockOffers: typeof deltas?.inStockOffers === "number" ? deltas.inStockOffers : null,
      });
      setMarketNote(typeof payload?.meta?.marketNote === "string" ? payload.meta.marketNote : null);
    } catch (e) {
      console.error(e);
      setListingsError(t("home.listingsLoadError"));
      setProducts([]);
    } finally {
      setListingsLoading(false);
    }
  }

  useEffect(() => {
    void fetchHealthSnapshot();
    void fetchAndGroupData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const formatPrice = (price: number) => {
    if (!price || price === Infinity) return t("common.notAvailable");
    return new Intl.NumberFormat("hu-HU").format(price) + " Ft";
  };

  const scrapeTime = healthInfo?.latestScrapeAt ? new Date(healthInfo.latestScrapeAt) : null;

  const formatScrapeTime = (value: Date | null) => {
    if (!value || Number.isNaN(value.getTime())) return "—";
    return value.toLocaleString(locale === "hu" ? "hu-HU" : "en-GB", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const formatRelativeAge = (minutes: number | null) => {
    if (minutes === null) return "—";
    if (minutes < 1) return t("health.justNow");
    if (minutes < 60) return t("health.minutesAgo", { minutes });
    const hours = Math.floor(minutes / 60);
    const rem = minutes % 60;
    if (rem === 0) return t("health.hoursAgo", { hours });
    return t("health.hoursMinutesAgo", { hours, minutes: rem });
  };

  const scrapeStatusLabel = () => {
    if (healthFetchFailed) return t("health.unknown");
    if (!healthInfo) return t("health.loading");
    if (healthInfo.badgeLevel === "red") return t("health.empty");
    const time = formatScrapeTime(scrapeTime);
    const age = formatRelativeAge(healthInfo.ageMinutes);
    return t("health.scrapeStatus", { time, age });
  };

  const healthTooltip = () => {
    if (healthFetchFailed) return t("health.loadFailed");
    if (!healthInfo) return t("health.loading");
    const age = healthInfo.ageMinutes !== null ? String(healthInfo.ageMinutes) : "—";
    return t("health.tooltipDetail", {
      prefix: t("health.tooltipPrefix"),
      age,
      inStock: healthInfo.totalInStockRows,
      total: healthInfo.totalRows,
    });
  };

  const healthDotClass = healthFetchFailed
    ? "bg-red-500"
    : !healthInfo
      ? "bg-gray-300"
      : healthInfo.badgeLevel === "red"
        ? "bg-red-500"
        : healthInfo.badgeLevel === "amber"
          ? "bg-amber-500"
          : "bg-emerald-500";

  const healthPillClass = healthFetchFailed
    ? "border-red-200 bg-red-50 text-red-900"
    : !healthInfo
      ? "border-gray-200 bg-white text-gray-500"
      : healthInfo.badgeLevel === "red"
        ? "border-red-200 bg-red-50 text-red-900"
        : healthInfo.badgeLevel === "amber"
          ? "border-amber-200 bg-amber-50 text-amber-900"
          : "border-emerald-200 bg-emerald-50 text-emerald-900";

  const filteredProducts = products.filter((p) => {
    const title = p.displayTitle.toLowerCase();

    const isEnglishProduct = (value: string) => {
      const text = value
        .toLowerCase()
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "");
      const nonEnglishMarkers = [
        "japan",
        "japanese",
        "japan ",
        "korean",
        "koreai",
        "chinese",
        "kinai",
        "deutsch",
        "french",
        "francia",
        "german",
        "nemet",
      ];
      return !nonEnglishMarkers.some((marker) => text.includes(marker));
    };

    if (languageFilter === "english" && !isEnglishProduct(p.displayTitle)) {
      return false;
    }

    if (activeFilter === "boxes") return title.includes("booster box") || title.includes("display");
    if (activeFilter === "bundles") return title.includes("booster bundle") || title.includes("bundle");
    if (activeFilter === "packs")
      return title.includes("booster pack") || (title.includes("booster") && title.includes("pack"));
    if (activeFilter === "etbs") return title.includes("elite trainer box") || title.includes("etb");
    if (activeFilter === "tins") return title.includes("tin") || title.includes("blister");
    return true;
  });

  const sortedFilteredProducts = useMemo(() => {
    const rows = [...filteredProducts];
    rows.sort((a, b) => {
      let cmp = 0;
      switch (sortColumn) {
        case "product":
          cmp = a.displayTitle.localeCompare(b.displayTitle, locale === "hu" ? "hu" : "en");
          break;
        case "lowestPrice":
          cmp = a.lowestPrice - b.lowestPrice;
          break;
        case "medianPrice":
          cmp = a.medianPrice - b.medianPrice;
          break;
        case "spread":
          cmp = a.spread - b.spread;
          break;
        case "bestVsMedian":
          cmp = a.bestVsMedian - b.bestVsMedian;
          break;
        case "offers":
          cmp = a.offers.length - b.offers.length;
          break;
        case "score":
        default:
          cmp = a.score - b.score;
          break;
      }
      return sortDirection === "asc" ? cmp : -cmp;
    });
    return rows;
  }, [filteredProducts, sortColumn, sortDirection, locale]);

  const sortButtonClass =
    "inline-flex items-center flex-nowrap gap-1.5 whitespace-nowrap font-bold uppercase tracking-wider hover:text-gray-700 transition-colors";
  const sortThClass = "p-4 align-middle whitespace-nowrap";

  const btnAct = "bg-[#a63c5e] text-white border-[#a63c5e]";
  const btnIna = "bg-white text-gray-700 border-gray-200 hover:bg-gray-50";

  if (selectedProduct) {
    return (
      <main className="min-h-screen bg-[#f1f0ec] text-gray-900 font-sans p-6 md:p-10">
        <div className="max-w-6xl mx-auto">
          <div className="mb-10">
            <AppBrand onNavigateHome={() => setSelectedProduct(null)} />
          </div>
          <button
            onClick={() => setSelectedProduct(null)}
            className="text-[#4b3585] font-bold text-sm flex items-center gap-2 mb-6 hover:opacity-80 transition-opacity uppercase tracking-wider"
          >
            ← {t("home.back")}
          </button>

          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden flex flex-col md:flex-row">
            <div className="bg-gray-50 p-10 md:w-1/2 flex items-center justify-center border-r border-gray-100">
              {selectedProduct.imageUrl ? (
                <img
                  src={selectedProduct.imageUrl}
                  alt={selectedProduct.displayTitle}
                  className="max-h-[400px] object-contain drop-shadow-xl hover:scale-105 transition-transform duration-300"
                />
              ) : (
                <div className="w-full h-64 bg-gray-200 rounded flex items-center justify-center text-gray-400 font-bold">
                  NO IMAGE
                </div>
              )}
            </div>

            <div className="p-8 md:p-12 md:w-1/2 flex flex-col">
              <h1 className="text-3xl font-extrabold text-gray-900 mb-4">{selectedProduct.displayTitle}</h1>

              <div className="flex items-center gap-4 mb-8">
                <span className="text-xs font-bold text-[#4b3585] uppercase tracking-wider">
                  {t("home.comparing")} {selectedProduct.offers.length} {t("home.storeOffers")}
                </span>
                {selectedProduct.medianPrice > 0 && (
                  <span className="bg-gray-100 text-gray-600 text-xs font-bold px-3 py-1 rounded-full">
                    {t("pricing.marketMedian")}: {formatPrice(selectedProduct.medianPrice)}
                  </span>
                )}
              </div>

              <div className="w-full h-px bg-gray-100 mb-6" />

              <div className="flex-1 overflow-y-auto space-y-6 pr-4">
                {selectedProduct.offers.map((offer, idx) => (
                  <div
                    key={idx}
                    className="flex justify-between items-center group bg-gray-50/80 border border-gray-100 rounded-xl px-4 py-3"
                  >
                    <div>
                      <h3 className="font-bold text-lg text-gray-900 group-hover:text-[#a63c5e] transition-colors">
                        {offer.shop_name}
                      </h3>
                      <p className="text-[10px] font-bold text-green-500 uppercase tracking-wider mt-1 flex items-center gap-1">
                        <span className="w-2 h-2 rounded-full bg-green-500 block"></span> {t("stock.inStock")}
                      </p>
                    </div>
                    <div className="text-right">
                      <div className="font-extrabold text-xl text-gray-900">{formatPrice(offer.price_huf)}</div>
                      <a
                        href={offer.product_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-[11px] font-bold text-[#a63c5e] uppercase tracking-wider mt-1 block hover:underline"
                      >
                        {t("home.viewDeal")} →
                      </a>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[#f1f0ec] text-gray-900 font-sans p-6 md:p-10">
      <div className="max-w-7xl mx-auto flex justify-between items-center mb-10">
        <AppBrand />

        <div className="flex items-center gap-3 flex-wrap justify-end">
          <div
            title={healthTooltip()}
            className={`hidden md:inline-flex items-center gap-2 text-xs font-semibold rounded-lg px-3 py-2 border cursor-default ${healthPillClass}`}
          >
            <span>🕒</span>
            <span className={`h-2 w-2 rounded-full shrink-0 ${healthDotClass}`} aria-hidden />
            <span className="whitespace-nowrap">{scrapeStatusLabel()}</span>
          </div>
          <div className="flex gap-2 bg-white rounded-lg p-1 shadow-sm border border-gray-200">
            <button
              onClick={() => router.replace(pathname, { locale: "en" })}
              className={`px-3 py-1 rounded-md text-sm font-bold ${locale === "en" ? "bg-[#a63c5e] text-white" : "text-gray-500"}`}
            >
              EN
            </button>
            <button
              onClick={() => router.replace(pathname, { locale: "hu" })}
              className={`px-3 py-1 rounded-md text-sm font-bold ${locale === "hu" ? "bg-[#a63c5e] text-white" : "text-gray-500"}`}
            >
              HU
            </button>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto">
        {listingsError ? (
          <div className="mb-6 flex flex-col gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-900 sm:flex-row sm:items-center">
            <span className="flex-1 font-semibold">{listingsError}</span>
            <button
              type="button"
              onClick={() => {
                void fetchHealthSnapshot();
                void fetchAndGroupData();
              }}
              className="shrink-0 rounded-lg bg-red-900 px-4 py-2 text-xs font-bold uppercase tracking-wide text-white hover:bg-red-800"
            >
              {t("common.retry")}
            </button>
          </div>
        ) : null}
        <h2 className="text-3xl font-bold mb-4">{t("home.pageTitle")}</h2>

        <section className="mb-6 max-w-3xl space-y-2 text-sm leading-relaxed text-gray-600">
          <p>{t("seo.introP1")}</p>
          <p>{t("seo.introP2")}</p>
        </section>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm">
            <div className="text-xs font-bold text-gray-500 uppercase tracking-wider">{t("bento.inStockProducts")}</div>
            <div className="text-2xl font-extrabold text-gray-900 mt-2">{products.length}</div>
            <StatDelta delta={statsDeltas.inStockProducts} label={t("bento.vsLastUpdate")} />
          </div>
          <div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm">
            <div className="text-xs font-bold text-gray-500 uppercase tracking-wider">{t("bento.shops")}</div>
            <div className="text-2xl font-extrabold text-gray-900 mt-2">{shopsCount}</div>
            <StatDelta delta={statsDeltas.shops} label={t("bento.vsLastUpdate")} />
          </div>
          <div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm">
            <div className="text-xs font-bold text-gray-500 uppercase tracking-wider">{t("bento.inStockOffers")}</div>
            <div className="text-2xl font-extrabold text-gray-900 mt-2">{totalOffers}</div>
            <StatDelta delta={statsDeltas.inStockOffers} label={t("bento.vsLastUpdate")} />
          </div>
          <div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm sm:col-span-2 lg:col-span-1">
            <div className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">{t("bento.metricsTitle")}</div>
            <div className="text-xs text-gray-600 space-y-1">
              <div>• {t("bento.metricOffers")}</div>
              <div>• {t("bento.metricMedian")}</div>
              <div>• {t("bento.metricGap")}</div>
              <div>• {t("bento.metricDelta")}</div>
            </div>
          </div>
        </div>

        <p
          title={healthTooltip()}
          className={`md:hidden text-xs font-semibold mb-4 inline-flex items-center gap-2 rounded-lg border px-3 py-2 cursor-default ${healthPillClass}`}
        >
          <span>🕒</span>
          <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${healthDotClass}`} aria-hidden />
          {scrapeStatusLabel()}
        </p>
      </div>

      {listingsLoading && products.length === 0 ? (
        <div className="max-w-7xl mx-auto py-24 text-center text-gray-600 font-semibold">{t("common.loading")}</div>
      ) : (
        <div className="max-w-7xl mx-auto">
          <div className="flex flex-wrap gap-2 overflow-x-auto pb-4 mb-4 scrollbar-hide">
              <button
                onClick={() => setActiveFilter("all")}
                className={`whitespace-nowrap px-4 py-1.5 rounded-lg text-sm font-bold transition-colors border ${activeFilter === "all" ? btnAct : btnIna}`}
              >
                {t("categories.all")}
              </button>
              <button
                onClick={() => setActiveFilter("boxes")}
                className={`whitespace-nowrap px-4 py-1.5 rounded-lg text-sm font-bold transition-colors border ${activeFilter === "boxes" ? btnAct : btnIna}`}
              >
                {t("categories.boosterBoxes")}
              </button>
              <button
                onClick={() => setActiveFilter("bundles")}
                className={`whitespace-nowrap px-4 py-1.5 rounded-lg text-sm font-bold transition-colors border ${activeFilter === "bundles" ? btnAct : btnIna}`}
              >
                {t("categories.bundles")}
              </button>
              <button
                onClick={() => setActiveFilter("packs")}
                className={`whitespace-nowrap px-4 py-1.5 rounded-lg text-sm font-bold transition-colors border ${activeFilter === "packs" ? btnAct : btnIna}`}
              >
                {t("categories.boosterPacks")}
              </button>
              <button
                onClick={() => setActiveFilter("etbs")}
                className={`whitespace-nowrap px-4 py-1.5 rounded-lg text-sm font-bold transition-colors border ${activeFilter === "etbs" ? btnAct : btnIna}`}
              >
                {t("categories.etbs")}
              </button>
              <button
                onClick={() => setActiveFilter("tins")}
                className={`whitespace-nowrap px-4 py-1.5 rounded-lg text-sm font-bold transition-colors border ${activeFilter === "tins" ? btnAct : btnIna}`}
              >
                {t("categories.tinsBlisters")}
              </button>
              <div className="w-px h-8 bg-gray-200 mx-1" />
              <button
                onClick={() => setLanguageFilter("all")}
                className={`whitespace-nowrap px-4 py-1.5 rounded-lg text-sm font-bold transition-colors border ${languageFilter === "all" ? btnAct : btnIna}`}
              >
                {t("filters.allLanguages")}
              </button>
              <button
                onClick={() => setLanguageFilter("english")}
                className={`whitespace-nowrap px-4 py-1.5 rounded-lg text-sm font-bold transition-colors border ${languageFilter === "english" ? btnAct : btnIna}`}
              >
                {t("filters.englishOnly")}
              </button>
            </div>

          <h3 className="font-bold text-lg mb-1 flex items-center gap-2">🔥 {t("home.trendingNow")}</h3>
          <p className="text-sm text-gray-500 mb-4">
            {marketNote || t("home.trendingSubtitle")}
          </p>

          <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="bg-white border-b border-gray-100 text-xs font-bold text-gray-400 uppercase tracking-wider">
                      <th className={`${sortThClass} w-12 text-center font-bold uppercase tracking-wider text-gray-400`}>
                        {t("table.headers.rank")}
                      </th>
                      <th className={sortThClass}>
                        <button
                          type="button"
                          onClick={() => toggleSort("product")}
                          className={sortButtonClass}
                          aria-label={t("table.sort.product")}
                        >
                          <span>{t("table.headers.product")}</span>
                          <SortIndicator active={sortColumn === "product"} direction={sortDirection} />
                        </button>
                      </th>
                      <th className={`${sortThClass} text-right`}>
                        <button
                          type="button"
                          onClick={() => toggleSort("lowestPrice")}
                          className={`${sortButtonClass} ml-auto`}
                          aria-label={t("table.sort.lowestPrice")}
                        >
                          <span>{t("table.headers.lowestPrice")}</span>
                          <SortIndicator active={sortColumn === "lowestPrice"} direction={sortDirection} />
                        </button>
                      </th>
                      <th className={`${sortThClass} text-right`}>
                        <button
                          type="button"
                          onClick={() => toggleSort("medianPrice")}
                          className={`${sortButtonClass} ml-auto`}
                          title={t("table.tooltips.median")}
                          aria-label={t("table.sort.median")}
                        >
                          <span>{t("table.headers.median")}</span>
                          <HeaderInfoIcon title={t("table.tooltips.median")} />
                          <SortIndicator active={sortColumn === "medianPrice"} direction={sortDirection} />
                        </button>
                      </th>
                      <th className={`${sortThClass} text-right`}>
                        <button
                          type="button"
                          onClick={() => toggleSort("spread")}
                          className={`${sortButtonClass} ml-auto`}
                          title={t("table.tooltips.spread")}
                          aria-label={t("table.sort.priceGap")}
                        >
                          <span>{t("table.headers.priceGap")}</span>
                          <HeaderInfoIcon title={t("table.tooltips.spread")} />
                          <SortIndicator active={sortColumn === "spread"} direction={sortDirection} />
                        </button>
                      </th>
                      <th className={`${sortThClass} text-right`}>
                        <button
                          type="button"
                          onClick={() => toggleSort("bestVsMedian")}
                          className={`${sortButtonClass} ml-auto`}
                          title={t("table.tooltips.delta")}
                          aria-label={t("table.sort.delta")}
                        >
                          <span>{t("table.headers.delta")}</span>
                          <HeaderInfoIcon title={t("table.tooltips.delta")} />
                          <SortIndicator active={sortColumn === "bestVsMedian"} direction={sortDirection} />
                        </button>
                      </th>
                      <th className={`${sortThClass} text-center`}>
                        <button
                          type="button"
                          onClick={() => toggleSort("offers")}
                          className={`${sortButtonClass} mx-auto`}
                          aria-label={t("table.sort.offers")}
                        >
                          <span>{t("table.headers.offers")}</span>
                          <SortIndicator active={sortColumn === "offers"} direction={sortDirection} />
                        </button>
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {sortedFilteredProducts.map((prod, idx) => (
                      <tr
                        key={idx}
                        onClick={() => setSelectedProduct(prod)}
                        className="hover:bg-gray-50 transition-colors cursor-pointer group"
                      >
                        <td className="p-4 text-center text-sm text-gray-400">{idx + 1}</td>
                        <td className="px-4 py-5 flex items-center gap-4 min-w-[280px]">
                          <div className="w-14 h-14 flex-shrink-0 flex items-center justify-center rounded-md border border-gray-100 bg-white p-1">
                            {prod.imageUrl ? (
                              <img
                                src={prod.imageUrl}
                                alt={prod.displayTitle}
                                className="max-h-full max-w-full object-contain"
                              />
                            ) : (
                              <div className="w-full h-full bg-gray-100 rounded" />
                            )}
                          </div>
                          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
                            <span className="font-bold text-base leading-snug text-[#4b3585] group-hover:text-[#a63c5e] transition-colors">
                              {prod.displayTitle}
                            </span>
                            {prod.trendingScore >= 75 ? (
                              <span className="shrink-0 rounded-full bg-orange-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-orange-700">
                                🔥 {t("home.trendingBadge")}
                              </span>
                            ) : null}
                          </div>
                        </td>
                        <td className="p-4 text-right font-bold text-sm whitespace-nowrap">
                          {formatPrice(prod.lowestPrice)}
                        </td>
                        <td className="p-4 text-right text-sm text-gray-500 whitespace-nowrap">
                          {formatPrice(prod.medianPrice)}
                        </td>
                        <td className="p-4 text-right text-sm text-gray-500 whitespace-nowrap">
                          {prod.spread === 0 ? "0 Ft" : formatPrice(prod.spread)}
                        </td>
                        <td
                          className={`p-4 text-right text-sm font-bold ${prod.bestVsMedian > 0 ? "text-red-500" : prod.bestVsMedian < 0 ? "text-green-500" : "text-gray-300"}`}
                        >
                          {prod.bestVsMedian !== 0 ? `${prod.bestVsMedian > 0 ? "+" : ""}${prod.bestVsMedian}%` : "-"}
                        </td>
                        <td className="p-4 text-center">
                          <span className="inline-flex items-center justify-center w-6 h-6 rounded bg-gray-100 text-xs font-bold text-gray-700">
                            {prod.offers.length}
                          </span>
                        </td>
                      </tr>
                    ))}
                    {sortedFilteredProducts.length === 0 && (
                      <tr>
                        <td colSpan={7} className="p-8 text-center text-sm text-gray-500">
                          {t("common.noData")}
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

          <section className="mt-10 rounded-xl border border-gray-100 bg-white p-6 shadow-sm">
            <h2 className="text-lg font-bold text-gray-900 mb-4">{t("seo.faqTitle")}</h2>
            <dl className="space-y-4 text-sm text-gray-600">
              <div>
                <dt className="font-bold text-gray-900">{t("seo.faqQ1")}</dt>
                <dd className="mt-1 leading-relaxed">{t("seo.faqA1")}</dd>
              </div>
              <div>
                <dt className="font-bold text-gray-900">{t("seo.faqQ2")}</dt>
                <dd className="mt-1 leading-relaxed">{t("seo.faqA2")}</dd>
              </div>
              <div>
                <dt className="font-bold text-gray-900">{t("seo.faqQ3")}</dt>
                <dd className="mt-1 leading-relaxed">{t("seo.faqA3")}</dd>
              </div>
            </dl>
          </section>
        </div>
      )}
    </main>
  );
}
