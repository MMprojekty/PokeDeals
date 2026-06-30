import type { ComparisonProduct } from "@/lib/listings";
import type { PriceHistoryPoint } from "@/lib/price-history";
import { ProductDetailClient } from "@/components/ProductDetailClient";

type ProductDetailProps = {
  product: ComparisonProduct;
  locale: string;
  lastUpdated: string | null;
  priceHistory?: PriceHistoryPoint[];
};

export function ProductDetail({
  product,
  locale,
  lastUpdated,
  priceHistory = [],
}: ProductDetailProps) {
  return (
    <ProductDetailClient
      product={{
        slug: product.slug,
        displayTitle: product.displayTitle,
        lowestPrice: product.lowestPrice,
        medianPrice: product.medianPrice,
        highestPrice: product.highestPrice,
        spread: product.spread,
        bestVsMedian: product.bestVsMedian,
        isNewSinceLastUpdate: product.isNewSinceLastUpdate,
        imageUrl: product.imageUrl,
        offers: product.offers.map((offer) => ({
          shop_name: offer.shopName,
          shop_slug: offer.shopSlug,
          price_huf: offer.priceHuf,
          product_url: offer.productUrl,
        })),
      }}
      locale={locale}
      lastUpdated={lastUpdated}
      priceHistory={priceHistory}
    />
  );
}
