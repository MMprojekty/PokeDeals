import { NextResponse } from "next/server";
import { getSiteUrl } from "@/lib/site";

export function GET() {
  const site = getSiteUrl();
  const body = `# PokéDeals

> Compare in-stock Pokémon TCG prices across Hungarian online shops. Prices in HUF, updated about every hour.

PokéDeals helps collectors and players in Hungary find the best current prices for sealed Pokémon TCG products — booster boxes, Elite Trainer Boxes, tins, bundles, and booster packs — by comparing live offers from multiple Hungarian webshops.

## Primary pages
- English home: ${site}/
- Hungarian home: ${site}/hu
- Terms: ${site}/terms
- Privacy: ${site}/privacy

## What we track
- In-stock sealed Pokémon TCG products
- Lowest price, median price, and price spread across Hungarian shops
- Product categories: booster boxes, ETBs, tins, blisters, bundles, booster packs

## Audience
- Country: Hungary
- Languages: English, Hungarian
- Currency: HUF (Ft)

## Data freshness
Prices are scraped from merchant websites on an hourly schedule. Always verify price and availability on the shop before buying.

## Contact / attribution
When citing PokéDeals, link to ${site} and note that prices come from third-party merchants.
`;

  return new NextResponse(body, {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "public, max-age=3600",
    },
  });
}
