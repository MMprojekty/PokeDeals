-- Legacy flat table used by the current scraper (shop_listings).
-- Run this FIRST if you are setting up a brand-new Supabase project.
create table if not exists public.shop_listings (
  id uuid primary key default gen_random_uuid(),
  shop_name text not null,
  raw_title text not null,
  price_huf integer not null check (price_huf >= 0),
  stock_status text not null default 'IN_STOCK',
  product_url text,
  image_url text,
  demand_score integer default 50,
  cm30 integer,
  cm7 integer,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists shop_listings_shop_name_idx on public.shop_listings (shop_name);
create index if not exists shop_listings_updated_at_idx on public.shop_listings (updated_at desc);

alter table public.shop_listings enable row level security;

drop policy if exists "Public read shop_listings" on public.shop_listings;
create policy "Public read shop_listings" on public.shop_listings for select using (true);

grant usage on schema public to service_role;
grant select, insert, update, delete on public.shop_listings to service_role;
grant select on public.shop_listings to anon, authenticated;
