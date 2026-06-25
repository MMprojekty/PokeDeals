# PokéDeals — clean project

**Your project folder:** `~/Downloads/PokeDeals`

Your project now has **only 3 folders**:

```
PokeDeals/
├── web/              ← Your dashboard DESIGN (the UI you keep)
├── scraper/          ← Collects prices from Hungarian shops
├── supabase/         ← One SQL file to create the database table
└── START_HERE.md     ← You are here
```

Nothing else. No old backup env files. No marketplace. No git history.

---

## Step 1 — Database (Supabase)

1. [supabase.com](https://supabase.com) → **New project**
2. **SQL Editor** → **New query**
3. Open `supabase/migrations/000000_shop_listings_legacy.sql` in Cursor
4. Copy all → paste in Supabase → **Run**
5. If scraper or website shows **permission denied for table shop_listings**, also run `supabase/migrations/000001_service_role_grants.sql`
6. **Settings → General** → copy **Project URL**
7. **Settings → API Keys → Legacy tab** → copy **service_role** key

---

## Step 2 — Website env file

1. In Cursor: **Cmd + P** → type `env.local.example` → open `web/.env.local.example`
2. **Cmd + A** → **Cmd + C** (copy all)
3. **Cmd + P** → type `env.local` → if file doesn't exist, right-click `web` folder → **New File** → name it `.env.local`
4. Paste your keys (replace the placeholder URL and key)
5. **Cmd + S**

---

## Step 3 — Run the dashboard

```bash
cd ~/Downloads/PokeDeals/web
npm install
npm run dev
```

Open **http://localhost:3000**

---

## Step 4 — Scraper (one-time manual run, optional)

Use this only if you want to test locally once. **For automatic updates, use Step 5 (GitHub — runs in the cloud).**

1. Copy `scraper/.env.example` → `scraper/.env`
2. Paste the same Supabase keys + your OpenAI key
3. Run:

```bash
cd ~/Downloads/PokeDeals/scraper
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
python scraper.py --headless
```

4. Refresh the browser — products appear.

---

## Step 5 — Automatic scraper in the cloud (GitHub Actions)

Nothing runs on your Mac in the background. GitHub runs the scraper on a schedule and writes to Supabase.

### A. Put the project on GitHub

1. Go to [github.com/new](https://github.com/new) → create a repo named `PokeDeals` (private recommended).
2. In Terminal:

```bash
cd ~/Downloads/PokeDeals
git init
git add .
git commit -m "Initial PokeDeals project"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/PokeDeals.git
git push -u origin main
```

Replace `YOUR-USERNAME` with your GitHub username.

### B. Add secrets (your API keys)

1. GitHub repo → **Settings** → **Secrets and variables** → **Actions**
2. **New repository secret** — add these three:

| Name | Value |
|------|--------|
| `SUPABASE_URL` | From Supabase → Settings → General → Project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | From Supabase → Settings → API Keys → Legacy → service_role |
| `OPENAI_API_KEY` | Your OpenAI key (`sk-...`) |

### C. Run it

1. GitHub repo → **Actions** tab
2. Click **Scrape shop prices** → **Run workflow** → **Run workflow**
3. Wait ~5–10 minutes. Green check = success.
4. Refresh **http://localhost:3000** — new prices appear.

After that it runs **automatically every day** at 06:00 UTC. No Mac background jobs.

---

## What was removed

| Deleted | Why |
|---------|-----|
| `marketplace/` | Different app, not your price dashboard |
| Old `.env` secrets | Dead database from backup |
| `.git/` | Fresh start (you can `git init` later) |
| Extra docs & scripts | One guide only: this file |

Your **design is untouched** in `web/app/[locale]/page.tsx`.
