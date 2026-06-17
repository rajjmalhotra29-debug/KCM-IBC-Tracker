"""FastAPI application entrypoint — serves the API and the single-page frontend."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import init_db
from .routers import auth, billing, buyers, dashboard, deals, matching, public

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup():
    init_db()


app.include_router(auth.router)
app.include_router(public.router)
app.include_router(dashboard.router)
app.include_router(buyers.router)
app.include_router(matching.router)
app.include_router(billing.router)
app.include_router(deals.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "app": settings.app_name, "ai_enabled": settings.ai_enabled}


# --- serve the frontend (mounted last so /api/* wins) ---
if FRONTEND_DIR.exists():
    @app.get("/")
    def index():
        return FileResponse(FRONTEND_DIR / "index.html")

    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="static")
