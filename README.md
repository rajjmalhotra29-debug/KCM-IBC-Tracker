# KCM IBC Finder (K C Mehta & Co)

Two deliverables that turn India's Insolvency & Bankruptcy (IBC) pipeline into
deal flow — sharing one daily IBBI data feed:

1. **`client.html` — PUBLIC viewer.** A free, daily-updated substitute for the IBBI
   website: the latest 100 companies in IBC (newest first), each with a Form G /
   process tracker, financial-snapshot panel, claims countdown, research links and
   an "Engage KCM" button. **Search + filters.** Contains **no client data and no
   fit-checking**. Safe to publish; linked from kcmehta.com.
2. **`master.html` — CONFIDENTIAL, KCM-only.** Everything the client file has, **plus**
   the firm's 2,056-company client master (AES-256-GCM **encrypted**, unlocked by the
   master password) and **in-browser merger-fit matching** of those clients against the
   live IBC companies — synergy fit, score, and 29A / reach / confidence gates. Add /
   edit clients (no limit) and change the password in Settings. Kept private; never published.

> Security: the client master exists only as ciphertext inside `master.html`; the
> password is never stored in the file. `client.html`/`data.json` contain zero client rows.

## Architecture

```
GitHub Action (daily)  ──scrape IBBI──►  site/data.json (IBBI companies only, latest 100)
                                              │
                 ┌────────────────────────────┴───────────────────────────┐
   client.html (PUBLIC, on Pages)                 master.html (PRIVATE, local, KCM only)
   fetches data.json                              fetches data.json + embedded ENCRYPTED
   core.css + core.js                             client master → password unlock →
   no client data, no matches                     core.css/core.js + master.js (matching)

backend/
  app/
    build_site.py    PUBLIC build → site/ (data.json + client.html + core.js/css)
    build_master.py  CONFIDENTIAL build → master/master.html (reads Excel, encrypts)
    extractor/ibbi.py  multi-page IBBI scraper
    matching/rules.py  rule engine (ported to JS in master.js)
    routers/, config.py, models.py …   (FastAPI app — optional dynamic/dev + future freemium)
  frontend/
    core.css, core.js          shared by both files
    client.html                public viewer
    master.js, master_template.html   master layer (crypto + matching + settings)
data/deals.json                aggregate track record (no names) for the public feed
```

## Build & run

**Public (client) site** — what gets deployed:
```powershell
cd backend; ../.venv/Scripts/python.exe -m app.build_site      # → ../site/ (data.json + client.html)
cd ../site; ../.venv/Scripts/python.exe -m http.server 8001    # preview → http://127.0.0.1:8001
```

**Confidential master file** — built locally, kept private:
```powershell
# set MASTER_PASSWORD (and optionally MASTER_XLSX) in backend/.env first
cd backend; ../.venv/Scripts/python.exe -m app.build_master    # → ../master/master.html
```
Open `master/master.html` in a browser → click **Unlock client matching** → enter the
master password (held in `backend/.env`, never written into the file) → matches appear.

Full deploy steps (repo, Pages, Anthropic secret, custom domain, linking from
kcmehta.com) are in **[DEPLOY.md](DEPLOY.md)**.

The original dynamic FastAPI app (`./run.ps1` → http://127.0.0.1:8000, with `index.html`
/ `app.js`, logins and the freemium tier) is retained for development and a future paid
backend, but the two HTML files above are the current deliverables.

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
