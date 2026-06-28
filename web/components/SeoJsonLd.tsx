import type { ClientComparisonRow } from "@/lib/listings-client";
import { absoluteUrl, getSiteUrl } from "@/lib/site";

type SeoJsonLdProps = {
  locale: string;
  products: ClientComparisonRow[];
};

export function SeoJsonLd({ locale, products }: SeoJsonLdProps) {
  const siteUrl = getSiteUrl();
  const pageUrl = absoluteUrl(locale);

  const website = {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: "PokéDeals",
    url: siteUrl,
    inLanguage: locale === "hu" ? "hu-HU" : "en-GB",
    description:
      locale === "hu"
        ? "Pokémon TCG árak összehasonlítása magyar webshopokban."
        : "Compare Pokémon TCG prices across Hungarian online shops.",
    potentialAction: {
      "@type": "SearchAction",
      target: `${pageUrl}?q={search_term_string}`,
      "query-input": "required name=search_term_string",
    },
  };

  const organization = {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: "PokéDeals",
    url: siteUrl,
    areaServed: {
      "@type": "Country",
      name: "Hungary",
    },
  };

  const itemList = {
    "@context": "https://schema.org",
    "@type": "ItemList",
    name:
      locale === "hu"
        ? "Pokémon TCG termékek magyar boltokban"
        : "Pokémon TCG products in Hungarian shops",
    itemListElement: products.slice(0, 20).map((product, index) => ({
      "@type": "ListItem",
      position: index + 1,
      item: {
        "@type": "Product",
        name: product.displayTitle,
        image: product.imageUrl || undefined,
        offers: {
          "@type": "AggregateOffer",
          lowPrice: product.lowestPrice,
          highPrice: product.highestPrice,
          priceCurrency: "HUF",
          offerCount: product.offers.length,
          availability: "https://schema.org/InStock",
        },
      },
    })),
  };

  const payload = [website, organization, itemList];

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(payload) }}
    />
  );
}
