import type { ComparisonProduct } from "@/lib/listings";
import { absoluteUrl } from "@/lib/site";

type ProductJsonLdProps = {
  locale: string;
  product: ComparisonProduct;
};

export function ProductJsonLd({ locale, product }: ProductJsonLdProps) {
  const pageUrl = absoluteUrl(locale, `/product/${product.slug}`);
  const payload = {
    "@context": "https://schema.org",
    "@type": "Product",
    name: product.displayTitle,
    image: product.imageUrl || undefined,
    url: pageUrl,
    offers: {
      "@type": "AggregateOffer",
      lowPrice: product.lowestPrice,
      highPrice: product.highestPrice,
      priceCurrency: "HUF",
      offerCount: product.offers.length,
      availability: "https://schema.org/InStock",
    },
  };

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(payload) }}
    />
  );
}
