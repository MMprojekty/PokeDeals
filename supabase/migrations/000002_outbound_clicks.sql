-- Anonymous outbound click tracking for shop deal links.
-- Run in Supabase SQL Editor after the shop_listings migration.

create table if not exists public.outbound_clicks (
  id uuid primary key default gen_random_uuid(),
  product_slug text not null,
  shop_slug text not null,
  price_huf integer,
  destination_url text not null,
  user_agent text,
  referrer text,
  created_at timestamptz not null default now()
);

create index if not exists outbound_clicks_created_at_idx
  on public.outbound_clicks (created_at desc);

create index if not exists outbound_clicks_product_slug_idx
  on public.outbound_clicks (product_slug);

alter table public.outbound_clicks enable row level security;

grant usage on schema public to service_role;
grant select, insert on public.outbound_clicks to service_role;
