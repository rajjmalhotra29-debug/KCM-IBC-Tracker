# Deploying KCM IBC Finder

Two deliverables:
- **`client.html` (PUBLIC)** — deployed free on GitHub Pages; a daily GitHub Action
  scrapes IBBI and publishes `data.json`. **No client data.** This is what's linked from kcmehta.com.
- **`master.html` (CONFIDENTIAL)** — built locally with `app.build_master`, kept private
  by KCM. **Never pushed to GitHub.**

```
GitHub Action (daily, free)  ->  site/data.json (+ client.html)  ->  GitHub Pages   [PUBLIC]
app.build_master (local)     ->  master/master.html (encrypted client list)         [PRIVATE — keep off the web]
```

## What's in the repo

| Path | Role |
|------|------|
| `backend/app/build_site.py` | PUBLIC build the daily Action runs (IBBI feed + client.html) |
| `backend/app/build_master.py` | LOCAL build for the confidential master file |
| `backend/frontend/` | `core.css`, `core.js` (shared), `client.html`, `master.js`, `master_template.html` |
| `data/deals.json` | aggregate **track record** (mandate count + ₹ value) shown on the public site — no names |
| `.github/workflows/build.yml` | the daily PUBLIC build + Pages deploy |
| `site/`, `master/` | generated output — **gitignored**, never committed |

> The client-master Excel and `master/master.html` are **never** in the repo. The master
> file's client list is AES-256-GCM encrypted; the password lives only in `backend/.env`
> (gitignored) and the user's head.

## A. Deploy the PUBLIC client site (≈10 minutes)

1. **Create a GitHub repo** (a **public** repo gives unlimited free Actions + Pages).
   Safe: the published `data.json` contains only IBBI public companies — **no client data**.

2. **Push this project** to the repo:
   ```bash
   cd "<this folder>"
   git init
   git add .
   git commit -m "KCM IBC Finder"
   git branch -M main
   git remote add origin https://github.com/<you>/<repo>.git
   git push -u origin main
   ```

3. **Turn on Pages:** repo **Settings → Pages → Build and deployment → Source = GitHub Actions**.

4. **Turn on AI (optional):** repo **Settings → Secrets and variables → Actions →
   New repository secret**, name `ANTHROPIC_API_KEY`, value `sk-ant-...`. The next
   build will enrich every company and rank matches with Claude. Without it, the
   site runs on the (free) rule-based engine.

5. **Set your leads inbox:** edit `CONTACT_EMAIL` in `.github/workflows/build.yml`
   (the "Engage KCM on this asset" buttons open a pre-filled email to it).

6. **Run it:** **Actions tab → "Build & deploy KCM IBC Finder" → Run workflow.**
   When it finishes, your site is live at
   `https://<you>.github.io/<repo>/`.

It then **rebuilds automatically every day at 7:00 AM IST**, and also whenever you
edit `data/deals.json` and push.

## B. The CONFIDENTIAL master file (never deployed)

Built and used locally by KCM:

1. Put the master password in `backend/.env` (gitignored): `MASTER_PASSWORD=...`
   (optionally `MASTER_XLSX=<path to the client Excel>` and, after the public site is
   live, `MASTER_FEED_URL=https://<you>.github.io/<repo>/data.json` so the master pulls
   the latest IBBI feed; otherwise it uses the snapshot baked in at build time).
2. Build it:
   ```powershell
   cd backend; ../.venv/Scripts/python.exe -m app.build_master   # → ../master/master.html
   ```
3. Keep `master/master.html` **private** — store it on your machine or SharePoint, not
   on the web. Open it in a browser → **Unlock client matching** → enter the password.
4. Re-run the build whenever the client Excel changes (or add clients in-app via Settings).

The client list is AES-256-GCM encrypted inside the file; the password is never written
to it. Even if the file leaked, the client data stays locked.

## Link it from kcmehta.com (your chosen integration)

Add a button / menu item on your website pointing to the Pages URL:

```html
<a href="https://<you>.github.io/<repo>/" target="_blank" rel="noopener">
  IBC Finder — distressed-asset opportunities
</a>
```

### Optional: a branded subdomain (free)
To serve it at `ibc.kcmehta.com` instead:
1. Repo **Settings → Pages → Custom domain** → enter `ibc.kcmehta.com`.
2. With your DNS provider, add a **CNAME** record: `ibc` → `<you>.github.io`.
3. GitHub provisions HTTPS automatically.

## Updating content
- **Public track-record numbers:** edit `data/deals.json`, commit, push → site rebuilds
  (aggregate only — no names appear publicly).
- **Force a public refresh now:** Actions tab → Run workflow.
- **Client master (private):** add/edit clients in `master.html` → Settings (persists in
  your browser), or update the Excel and re-run `app.build_master`.
- **Change the master password:** `master.html` → Settings → Change password (enter the
  current password twice, then the new one).

## When you're ready to monetize (freemium)
Logins + payments + a hosted private backend need a small always-on server (the FastAPI
app in `backend/` already supports this — `ACCESS_MODE=freemium`). Host it on a low-cost
service (~$7/mo) when you charge for the matching. The two static files cover the free
public viewer and the internal master today.
