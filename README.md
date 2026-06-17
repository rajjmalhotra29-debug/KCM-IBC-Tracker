# Jarvis — IBC Origination Desk (K C Mehta & Co)

A **freemium web app** that turns India's Insolvency & Bankruptcy (IBC) pipeline
into deal flow for cash-rich acquirers. Styled as the **Jarvis** origination desk.

- **Free / anonymous** — anyone browses the live opportunity feed: each distressed
  company (CIRP / liquidation) shown as a card with a **Form G / process tracker**,
  a **financial snapshot** panel, claims-deadline countdown, and "Find on IBBI".
  The ranked client matches are **locked** (count advertised, details hidden).
- **Paid tier** — the **ranked client matches** unlock: each shows synergy fit
  (**backward / forward / horizontal**), a 0–100 score bar, the keywords matched,
  and three gates — **29A eligibility · KCM reach · data confidence**.

The dashboard renders from `GET /api/dashboard`; matches are the firm's "house
book" (MatchResults against the admin-owned client roster), gated by tier.

> Example: distressed *Martina Bio Genics* (pharma) → the engine surfaces Cadila,
> Zydus and Parul Chemicals for backward / horizontal integration.

## Architecture

```
backend/
  app/
    config.py        env-driven settings (AI & payments off until keys added)
    database.py      SQLAlchemy + SQLite (swap DATABASE_URL for Postgres)
    models.py        User, Target, Buyer, MatchResult
    security.py      JWT auth + freemium paywall gate (require_paid)
    extractor/       pluggable source scrapers — ibbi.py (default), generic.py
    matching/        rules.py (cheap filter) + ai.py (Claude) + engine.py (hybrid)
    importer.py      Excel/CSV buyer import
    routers/         auth, public (feed), buyers, matching, billing
    seed.py          demo users + targets + buyers
  frontend/          single-page UI (index.html + app.js, Tailwind CDN)
```

## Two ways to run it

**A. Dynamic (local dev / future freemium)** — the full FastAPI app with logins,
live refresh, admin editing:
```powershell
./run.ps1          # from the project root → http://127.0.0.1:8000
```

**B. Static (free GitHub hosting — the current launch path)** — a daily GitHub
Action runs `python -m app.build_site` (scrape + match + AI), writes `site/data.json`,
and GitHub Pages serves the frontend. Free, no server. Build locally to preview:
```powershell
cd backend; ../.venv/Scripts/python.exe -m app.build_site   # writes ../site/
cd ../site; ../.venv/Scripts/python.exe -m http.server 8001  # → http://127.0.0.1:8001
```
Full deploy steps (repo, Pages, the Anthropic secret, custom domain, linking from
kcmehta.com) are in **[DEPLOY.md](DEPLOY.md)**.

Demo logins (created by the seed):
- **Desk admin** (owns the client book, can refresh the feed + recompute matches):
  `admin@ibc.local` / `admin123`
- **Paid subscriber**: `buyer@ibc.local` / `buyer123`

New visitors can sign up (free tier) and use the **Unlock (demo)** button to test
the premium path without real payment. The seed loads 10 real opportunities, 21
client companies, and 30 matches from the Jarvis snapshot.

## Switching things on later

Edit `backend/.env` (already created; gitignored):

| Want | Set |
|------|-----|
| **AI matching + enrichment** | paste `ANTHROPIC_API_KEY=sk-ant-...` then restart. The engine auto-upgrades from rules → AI, and the daily ingest infers each new company's sector/products/inputs/customers from its name for far sharper matches. |
| **Brand / theme prototype** | `BRAND=kcm` ("KCM IBC Finder", Navy & Gold) or `BRAND=jarvis` (original warm desk). Both ship in one codebase. |
| Freemium (gated) instead of open | `ACCESS_MODE=freemium` |
| Feed size / freshness | `SCRAPE_MAX_PAGES` (IBBI pages × 20), `RETENTION_DAYS` (rolling window) |
| A different source site | `SOURCE_URL`, `SOURCE_ADAPTER` (+ optionally a new adapter class) |
| Real payments | `PAYMENTS_ENABLED=true`, `RAZORPAY_KEY_ID/SECRET` (`pip install razorpay`) |
| Shared Postgres DB | `DATABASE_URL=postgresql+psycopg://…` |

## Feed scale & retention

Each scrape walks `SCRAPE_MAX_PAGES` IBBI pages (default 12 → ~240 records) and
keeps a rolling window: a record stays if it was announced within `RETENTION_DAYS`
(default 30) **or** its bidding window is still open; older lapsed live records are
pruned. The seed showcase is exempt. The frontend paginates 30 cards at a time.

## Track record (deals)

Admin-maintained closed mandates power two hero stats — **Mandates Closed** and
**Value Created (FMV ₹ cr)** — shown to everyone. In `freemium`, free visitors see
the counts; paid users see the companies. Admin manages them via **Desk login →
View mandates → Add mandate** (`/api/deals` CRUD, admin-only).

## Daily auto-refresh (Windows)

A scheduled task **"Jarvis IBC Daily Ingest"** runs `python -m app.ingest` every
day at **7:00 AM** (battery-friendly; launched via `cmd.exe` to avoid the
console-app Ctrl+C issue). It scrapes IBBI, ingests new opportunities, AI-enriches
them (if a key is set), and recomputes matches. Output appends to `tools/ingest.log`.
Re-create / adjust it from `tools/` or Task Scheduler; run on demand with the
in-app **Refresh from IBBI** button.

## Financial-data research switches

Each opportunity card carries one-click deep-links to pull the company's
financials without leaving Jarvis:
- **Listed** companies → **Screener** (ratios) + **Tofler**.
- **Private** companies → **Tofler** (free filings) + **VCCEdge** (subscription).

Listed vs private is detected from the company name; links open a pre-filled
search in a new tab.

## Live data — the IBBI scrape

The default source is the live IBBI register: **https://ibbi.gov.in/public-announcement**.
The `ibbi` adapter reads the real table columns (Type of PA, Date of Announcement,
Last date of Submission, Corporate Debtor, Applicant, Insolvency Professional),
derives the stage (CIRP / liquidation) and estimates the Form G date (~75 days
after a CIRP admission).

Pull fresh opportunities three ways:
- **Daily job (recommended):** `python -m app.ingest` — scrape → ingest new
  targets → recompute client matches. Point Windows Task Scheduler at it to run
  every morning.
- **In-app button:** "Refresh from IBBI" (open in `open` mode; admin-only in
  `freemium`).
- **API:** `POST /api/refresh`.

### Adding another source site

1. Paste its URL into `SOURCE_URL` and set `SOURCE_ADAPTER`.
2. If it's a plain table, the `generic` adapter often works as-is.
3. For a tuned parser, copy `extractor/ibbi.py`, adjust the column patterns, and
   register it in `extractor/__init__.py:ADAPTERS`.

## Status

Phase 1 — fully runnable locally. Before public launch: real payment keys,
production `SECRET_KEY`, HTTPS + a host (Render/Railway/VPS), and the
site-specific extractor tuned to your chosen source.
