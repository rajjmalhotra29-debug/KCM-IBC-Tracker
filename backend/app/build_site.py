"""Static-site build — scrape IBBI + match + AI-enrich, then emit site/data.json.

This is what makes free GitHub hosting work: GitHub Pages serves the static
frontend, and a daily GitHub Action runs THIS script to regenerate the data.
It reuses the live app's scrape/match/dashboard logic against a throwaway DB,
so the static site and the dynamic app never diverge.

Run locally:   python -m app.build_site
In CI:         runs daily with ANTHROPIC_API_KEY provided as a GitHub secret.
"""
import json
import shutil
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .config import settings
from .database import Base
from .extractor import get_adapter
from .models import Buyer, Deal
from .routers.dashboard import build_dashboard
from .routers.public import ingest

ROOT = Path(__file__).resolve().parents[2]          # ibc-matchmaker/
DATA = ROOT / "data"                                # buyers.json, deals.json
SITE = ROOT / "site"                                # GitHub Pages root (output)
FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
BUILD_DB = Path(__file__).resolve().parents[1] / "build.db"   # throwaway


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def main() -> None:
    if BUILD_DB.exists():
        BUILD_DB.unlink()
    engine = create_engine(f"sqlite:///{BUILD_DB.as_posix()}",
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    try:
        for b in _load(DATA / "buyers.json", []):
            db.add(Buyer(**b))
        for d in _load(DATA / "deals.json", []):
            db.add(Deal(**d))
        db.commit()

        adapter = get_adapter(settings.source_adapter)
        found, new = ingest(db, adapter, settings.source_url, rematch=True)

        dash = build_dashboard(db, None)            # open access, no user
        SITE.mkdir(parents=True, exist_ok=True)
        (SITE / "data.json").write_text(
            json.dumps(dash.model_dump(), ensure_ascii=False), encoding="utf-8")
        for f in ("index.html", "app.js"):
            shutil.copy(FRONTEND / f, SITE / f)
        (SITE / ".nojekyll").write_text("", encoding="utf-8")   # serve files as-is

        print(f"[build] fetched={found} new={new} | opportunities={len(dash.opportunities)} "
              f"| deals={dash.track_record.deals_closed} (INR {dash.track_record.value_fmv_inr_cr}cr) "
              f"| AI={'on' if settings.ai_enabled else 'off'}")
        print(f"[build] wrote {SITE / 'data.json'} and copied frontend -> {SITE}")
    finally:
        db.close()
        engine.dispose()
        if BUILD_DB.exists():
            BUILD_DB.unlink()


if __name__ == "__main__":
    main()
