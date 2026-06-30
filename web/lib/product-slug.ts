import { canonicalKey } from "@/lib/listings";

/** URL-safe slug from a product title or canonical key. */
export function toProductSlug(titleOrKey: string): string {
  const key = titleOrKey.includes(" ")
    ? canonicalKey(titleOrKey)
    : titleOrKey.replace(/-/g, " ");
  return canonicalKey(key || titleOrKey).replace(/\s+/g, "-");
}

export function findProductSlug(displayTitle: string, productId?: string): string {
  if (productId && !productId.includes(" ")) {
    return productId.includes("-") ? productId : toProductSlug(productId);
  }
  return toProductSlug(displayTitle);
}

export function slugMatchesProduct(displayTitle: string, slug: string, productId?: string): boolean {
  const normalized = slug.toLowerCase();
  return (
    findProductSlug(displayTitle, productId) === normalized ||
    toProductSlug(displayTitle) === normalized ||
    canonicalKey(displayTitle).replace(/\s+/g, "-") === normalized
  );
}
