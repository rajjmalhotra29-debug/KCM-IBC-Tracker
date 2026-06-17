"""Daily job: scrape the IBBI register, ingest new opportunities, recompute matches.

Run manually:   python -m app.ingest
Scheduled daily by the "Jarvis IBC Daily Ingest" Windows task.
Writes its own log line to tools/ingest.log so it doesn't depend on the shell.
"""
from datetime import datetime
from pathlib import Path

from .config import settings
from .database import SessionLocal, init_db
from .extractor import get_adapter
from .routers.public import ingest as _ingest

LOG_FILE = Path(__file__).resolve().parents[2] / "tools" / "ingest.log"


def _log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def run(url: str | None = None, adapter: str | None = None):
    init_db()
    src = url or settings.source_url
    adp = get_adapter(adapter or settings.source_adapter)
    db = SessionLocal()
    try:
        found, new = _ingest(db, adp, src, rematch=True)
        _log(f"{adp.name} {src} — fetched {found}; {new} new; "
             f"matches {'recomputed' if new else 'unchanged'}; "
             f"AI={'on' if settings.ai_enabled else 'off'}")
    except Exception as e:  # never let the daily job crash silently
        _log(f"ERROR {type(e).__name__}: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run()
