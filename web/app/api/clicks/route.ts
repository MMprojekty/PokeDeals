import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

export const revalidate = 0;

type ClickPayload = {
  productSlug?: string;
  shopSlug?: string;
  priceHuf?: number;
  destinationUrl?: string;
};

export async function POST(request: Request) {
  const supabaseUrl = process.env.SUPABASE_URL;
  const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!supabaseUrl || !serviceRoleKey) {
    return NextResponse.json({ ok: false, reason: "not_configured" }, { status: 503 });
  }

  let body: ClickPayload;
  try {
    body = (await request.json()) as ClickPayload;
  } catch {
    return NextResponse.json({ ok: false, reason: "invalid_json" }, { status: 400 });
  }

  const productSlug = String(body.productSlug || "").trim().slice(0, 200);
  const shopSlug = String(body.shopSlug || "").trim().slice(0, 120);
  const destinationUrl = String(body.destinationUrl || "").trim().slice(0, 2000);
  const priceHuf = Number(body.priceHuf);

  if (!productSlug || !shopSlug || !destinationUrl) {
    return NextResponse.json({ ok: false, reason: "missing_fields" }, { status: 400 });
  }

  const supabase = createClient(supabaseUrl, serviceRoleKey);
  const { error } = await supabase.from("outbound_clicks").insert({
    product_slug: productSlug,
    shop_slug: shopSlug,
    price_huf: Number.isFinite(priceHuf) && priceHuf > 0 ? Math.round(priceHuf) : null,
    destination_url: destinationUrl,
    user_agent: request.headers.get("user-agent")?.slice(0, 500) ?? null,
    referrer: request.headers.get("referer")?.slice(0, 500) ?? null,
  });

  if (error) {
    return NextResponse.json(
      { ok: false, reason: error.code === "42P01" ? "table_missing" : "insert_failed" },
      { status: error.code === "42P01" ? 503 : 500 },
    );
  }

  return NextResponse.json({ ok: true });
}
