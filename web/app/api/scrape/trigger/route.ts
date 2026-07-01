import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.SUPABASE_URL;
const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
const listingsTable = process.env.SUPABASE_LISTINGS_TABLE || "shop_listings";
const githubToken = process.env.GITHUB_TOKEN;
const githubRepo = process.env.GITHUB_REPO || "MMprojekty/PokeDeals";

const TRIGGER_AFTER_MINUTES = Number(process.env.SCRAPE_TRIGGER_AFTER_MINUTES || 32);
const COOLDOWN_MINUTES = Number(process.env.SCRAPE_TRIGGER_COOLDOWN_MINUTES || 20);

export const revalidate = 0;

async function getAgeMinutes(): Promise<number | null> {
  if (!supabaseUrl || !serviceRoleKey) {
    return null;
  }

  const supabase = createClient(supabaseUrl, serviceRoleKey);
  const { data, error } = await supabase
    .from(listingsTable)
    .select("updated_at")
    .order("updated_at", { ascending: false })
    .limit(1);

  if (error || !data?.length) {
    return null;
  }

  const latest = data[0]?.updated_at;
  if (!latest) {
    return null;
  }

  const epoch = new Date(latest).getTime();
  if (!Number.isFinite(epoch)) {
    return null;
  }

  return Math.floor((Date.now() - epoch) / 60000);
}

async function getLastRunCreatedAt(): Promise<number | null> {
  if (!githubToken) {
    return null;
  }

  const response = await fetch(
    `https://api.github.com/repos/${githubRepo}/actions/workflows/scraper.yml/runs?per_page=1`,
    {
      headers: {
        Authorization: `Bearer ${githubToken}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      cache: "no-store",
    },
  );

  if (!response.ok) {
    return null;
  }

  const payload = await response.json().catch(() => null);
  const run = payload?.workflow_runs?.[0];
  if (!run?.created_at) {
    return null;
  }

  const epoch = new Date(run.created_at).getTime();
  return Number.isFinite(epoch) ? epoch : null;
}

async function scrapeInProgress(): Promise<boolean> {
  if (!githubToken) {
    return false;
  }

  for (const status of ["in_progress", "queued", "waiting", "pending"]) {
    const response = await fetch(
      `https://api.github.com/repos/${githubRepo}/actions/workflows/scraper.yml/runs?status=${status}&per_page=5`,
      {
        headers: {
          Authorization: `Bearer ${githubToken}`,
          Accept: "application/vnd.github+json",
          "X-GitHub-Api-Version": "2022-11-28",
        },
        cache: "no-store",
      },
    );
    if (!response.ok) {
      continue;
    }
    const payload = await response.json().catch(() => null);
    if ((payload?.workflow_runs?.length ?? 0) > 0) {
      return true;
    }
  }
  return false;
}

export async function POST() {
  if (!githubToken) {
    return NextResponse.json(
      { triggered: false, reason: "missing_github_token" },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }

  const ageMinutes = await getAgeMinutes();
  if (ageMinutes === null) {
    return NextResponse.json(
      { triggered: false, reason: "no_data", ageMinutes },
      { headers: { "Cache-Control": "no-store" } },
    );
  }

  if (ageMinutes < TRIGGER_AFTER_MINUTES) {
    return NextResponse.json(
      { triggered: false, reason: "fresh", ageMinutes },
      { headers: { "Cache-Control": "no-store" } },
    );
  }

  if (await scrapeInProgress()) {
    return NextResponse.json(
      { triggered: false, reason: "in_progress", ageMinutes },
      { headers: { "Cache-Control": "no-store" } },
    );
  }

  const lastRunAt = await getLastRunCreatedAt();
  if (lastRunAt !== null && Date.now() - lastRunAt < COOLDOWN_MINUTES * 60_000) {
    return NextResponse.json(
      { triggered: false, reason: "cooldown", ageMinutes },
      { headers: { "Cache-Control": "no-store" } },
    );
  }

  const dispatch = await fetch(
    `https://api.github.com/repos/${githubRepo}/actions/workflows/scraper.yml/dispatches`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${githubToken}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ ref: "main", inputs: { force: "true" } }),
      cache: "no-store",
    },
  );

  if (!dispatch.ok) {
    const detail = await dispatch.text().catch(() => "");
    return NextResponse.json(
      { triggered: false, reason: "github_error", ageMinutes, detail },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }

  return NextResponse.json(
    { triggered: true, reason: "stale", ageMinutes },
    { headers: { "Cache-Control": "no-store" } },
  );
}
