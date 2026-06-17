# Deploying KCM IBC Finder — free, on GitHub

The site is a **static frontend** plus a **daily GitHub Action** that scrapes IBBI,
runs the matching (and AI, if enabled), and publishes the data. No server, no cost.

```
GitHub Action (daily, free)  ->  builds site/data.json  ->  GitHub Pages serves it
```

## What's in the repo

| Path | Role |
|------|------|
| `backend/` | the app + `app/build_site.py` (the build script the Action runs) |
| `data/buyers.json` | the **client book** matching runs against — edit this to add/remove clients |
| `data/deals.json` | the **track record** (mandates + FMV) — edit this to update the numbers |
| `.github/workflows/build.yml` | the daily build + Pages deploy |
| `site/` | generated output (not committed; the Action rebuilds it) |

## One-time setup (≈10 minutes)

1. **Create a GitHub repo** (a **public** repo is simplest and gives unlimited free
   Actions + Pages). Note: in the current *open* prototype the client matches and
   deal values are shown publicly on the site by design — so a public repo exposes
   nothing the site doesn't already. (Going *freemium* later moves that data behind
   a paid backend.)

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
edit `data/buyers.json` or `data/deals.json` and push.

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
- **Add/remove a client:** edit `data/buyers.json`, commit, push → rebuilds.
- **Add a closed mandate:** edit `data/deals.json`, commit, push → the track-record
  numbers update.
- **Force a refresh now:** Actions tab → Run workflow.

## When you're ready to monetize (freemium)
Logins + payments + private client data need a small always-on backend (the FastAPI
app in `backend/` already does all of this — set `ACCESS_MODE=freemium`). Host it on
a low-cost service (~$7/mo) and point the frontend at it. The codebase already
supports both; nothing needs rewriting.
