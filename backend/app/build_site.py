"""PUBLIC static-site build — scrape IBBI, emit site/data.json + client.html.

GitHub Pages serves the static frontend; a daily GitHub Action runs THIS script
to regenerate the data. The PUBLIC feed deliberately contains **no client data
and no matches** — only the IBBI companies (latest 100, newest first) plus an
AGGREGATE track record (mandate count + ₹ value, no names). The confidential
master file is built separately by app.build_master.

Run locally:   python -m app.build_site
In CI:         runs daily (ANTHROPIC_API_KEY optional, only enriches target sectors).
"""
import json
import shutil
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .config import settings
from .database import Base
from .extractor import get_adapter
from .models import Deal
from .routers.dashboard import build_dashboard
from .routers.public import ingest, _parse_date

ROOT = Path(__file__).resolve().parents[2]          # ibc-matchmaker/
DATA = ROOT / "data"                                # deals.json (aggregate only)
SITE = ROOT / "site"                                # GitHub Pages root (output)
FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
BUILD_DB = Path(__file__).resolve().parents[1] / "build.db"   # throwaway

PUBLIC_LIMIT = 100                                   # latest N companies to publish
PUBLIC_FILES = ("client.html", "core.js", "core.css")


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _ann(o) -> date:
    t = o.target
    return _parse_date(t.admit) or _parse_date(t.announcement_date) or date.min


def main() -> None:
    if BUILD_DB.exists():
        BUILD_DB.unlink()
    engine = create_engine(f"sqlite:///{BUILD_DB.as_posix()}",
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    try:
        # deals → aggregate track record only (NO buyers loaded → NO matches)
        for d in _load(DATA / "deals.json", []):
            db.add(Deal(**d))
        db.commit()

        adapter = get_adapter(settings.source_adapter)
        found, new = ingest(db, adapter, settings.source_url, rematch=False, prune=False)

        dash = build_dashboard(db, None)            # open access, no user, no matches
        # newest first, then collapse repeat announcements of the SAME company
        # (IBBI lists a corporate debtor under several public announcements) so each
        # company shows once — its latest announcement — then take the latest N.
        dash.opportunities.sort(key=_ann, reverse=True)
        seen, uniq = set(), []
        for o in dash.opportunities:
            key = (o.target.name or "").strip().upper()
            if key in seen:
                continue
            seen.add(key)
            uniq.append(o)
        dash.opportunities = uniq[:PUBLIC_LIMIT]
        # web-research a short profile per company (cached; needs ANTHROPIC_API_KEY)
        from .enrich import enrich
        attached, researched = enrich(dash.opportunities, settings.anthropic_api_key, settings.ai_model)
        # aggregate track record only — never expose client/target names publicly
        dash.track_record.deals = []
        dash.track_record.locked = False

        if SITE.exists():
            shutil.rmtree(SITE)                     # drop any stale files
        SITE.mkdir(parents=True, exist_ok=True)
        (SITE / "data.json").write_text(
            json.dumps(dash.model_dump(), ensure_ascii=False), encoding="utf-8")
        # client.html with the Engage config injected; published as index too
        chtml = (FRONTEND / "client.html").read_text(encoding="utf-8")
        chtml = chtml.replace('window.ENGAGE_FORM_URL = "";', f'window.ENGAGE_FORM_URL = "{settings.engage_form_url}";')
        chtml = chtml.replace('window.ENGAGE_KEY = "";', f'window.ENGAGE_KEY = "{settings.engage_key}";')
        (SITE / "index.html").write_text(chtml, encoding="utf-8")
        (SITE / "client.html").write_text(chtml, encoding="utf-8")
        shutil.copy(FRONTEND / "core.js", SITE / "core.js")
        shutil.copy(FRONTEND / "core.css", SITE / "core.css")
        (SITE / ".nojekyll").write_text("", encoding="utf-8")

        # also emit ONE self-contained file (inline css/js + embedded feed) for easy offline review
        review = ROOT / "review"
        review.mkdir(parents=True, exist_ok=True)
        chtml = (FRONTEND / "client.html").read_text(encoding="utf-8")
        chtml = chtml.replace('window.ENGAGE_FORM_URL = "";', f'window.ENGAGE_FORM_URL = "{settings.engage_form_url}";')
        chtml = chtml.replace('window.ENGAGE_KEY = "";', f'window.ENGAGE_KEY = "{settings.engage_key}"; window.DATA_URL = "{settings.live_feed_url}";')
        chtml = chtml.replace('<link rel="stylesheet" href="core.css?v=7">',
                              "<style>\n" + (FRONTEND / "core.css").read_text(encoding="utf-8") + "\n</style>")
        feed_json = json.dumps(dash.model_dump(), ensure_ascii=False)
        chtml = chtml.replace('<script src="core.js?v=7"></script>',
                              "<script>window.EMBEDDED_FEED=" + feed_json + ";</script>\n<script>\n"
                              + (FRONTEND / "core.js").read_text(encoding="utf-8") + "\n</script>")
        (review / "KCM-IBC-Finder-PUBLIC.html").write_text(chtml, encoding="utf-8")

        print(f"[build] fetched={found} new={new} | published={len(dash.opportunities)} "
              f"(latest {PUBLIC_LIMIT}, newest-first) | track record={dash.track_record.deals_closed} "
              f"mandates / INR {dash.track_record.value_fmv_inr_cr}cr (aggregate) "
              f"| AI={'on' if settings.ai_enabled else 'off'}")
        print(f"[build] wrote {SITE / 'data.json'} + client.html/core.js/core.css -> {SITE}")
        print(f"[build] review (self-contained): {review / 'KCM-IBC-Finder-PUBLIC.html'}")
    finally:
        db.close()
        engine.dispose()
        if BUILD_DB.exists():
            BUILD_DB.unlink()


if __name__ == "__main__":
    main()
