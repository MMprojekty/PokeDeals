-- Run this if scraper/web get "permission denied for table shop_listings".
-- Safe to run multiple times.

grant usage on schema public to service_role;
grant select, insert, update, delete on public.shop_listings to service_role;
grant select on public.shop_listings to anon, authenticated;
