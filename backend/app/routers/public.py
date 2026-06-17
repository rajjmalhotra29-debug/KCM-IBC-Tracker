"""Public (free-tier) IBC company feed + source refresh.

The feed is open to everyone — the free hook. Refreshing from the source site is
admin-gated so anonymous traffic can't hammer the source.
"""
import re

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from fastapi import HTTPException, status

from ..config import settings
from ..database import get_db
from ..extractor import get_adapter
from ..matching import match_buyer_against_targets
from ..models import Buyer, Target, User
from ..schemas import ExtractResult, TargetOut
from ..security import get_current_user_optional

router = APIRouter(prefix="/api", tags=["public"])


def allow_ingest(user: User | None = Depends(get_current_user_optional)) -> User | None:
    """Refresh is open in 'open' mode; otherwise admin-only."""
    if settings.is_open:
        return user
    if not user or not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")
    return user


@router.get("/targets", response_model=list[TargetOut])
def list_targets(
    q: str | None = Query(None, description="search name/sector/products"),
    status: str | None = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    query = db.query(Target)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            Target.name.ilike(like), Target.sector.ilike(like),
            Target.products.ilike(like), Target.description.ilike(like),
        ))
    if status:
        query = query.filter(Target.status.ilike(f"%{status}%"))
    rows = query.order_by(Target.created_at.desc()).offset(offset).limit(limit).all()
    return rows


@router.get("/targets/{target_id}", response_model=TargetOut)
def get_target(target_id: int, db: Session = Depends(get_db)):
    from fastapi import HTTPException
    t = db.get(Target, target_id)
    if not t:
        raise HTTPException(404, "Not found")
    return t


@router.get("/source")
def source_info():
    return {
        "source_url": settings.source_url,
        "adapter": settings.source_adapter,
        "ai_enabled": settings.ai_enabled,
        "payments_enabled": settings.payments_enabled,
    }


@router.post("/refresh", response_model=ExtractResult)
def refresh_targets(
    url: str | None = Query(None, description="override source URL"),
    adapter: str | None = Query(None, description="ibbi|generic"),
    rematch: bool = Query(True, description="recompute client matches after ingest"),
    _: User | None = Depends(allow_ingest),
    db: Session = Depends(get_db),
):
    src = url or settings.source_url
    adp = get_adapter(adapter or settings.source_adapter)
    found, new = ingest(db, adp, src, rematch=rematch)
    return ExtractResult(
        source_url=src, adapter=adp.name, found=found, new=new,
        message=f"Fetched {found} record(s); {new} new added"
                + (", matches recomputed." if rematch and new else "."),
    )


def ingest(db: Session, adapter, src: str, rematch: bool = True) -> tuple[int, int]:
    """Scrape -> upsert targets -> AI-enrich new ones -> recompute house-book matches
    -> prune stale records. Returns (found, new). Shared by route + daily job."""
    from ..matching import ai  # local import keeps optional dep lazy

    companies = adapter.extract(src, max_pages=settings.scrape_max_pages)
    new_targets: list[Target] = []
    for c in companies:
        ref = c.source_ref()
        if db.query(Target).filter(Target.source_ref == ref).first():
            continue
        t = Target(
            name=c.name, sector=c.sector, products=c.products,
            raw_materials=c.raw_materials, customers=c.customers,
            description=c.description, status=c.status, process_type=c.process_type,
            resolution_professional=c.resolution_professional, location=c.location,
            announcement_date=c.announcement_date, source_url=c.source_url, source_ref=ref,
            is_liq=c.is_liq, stage_label=c.stage_label, stage_class=c.stage_class,
            applicant=c.applicant, admit=c.admit, claims_by=c.claims_by, form_g_by=c.form_g_by,
        )
        db.add(t)
        new_targets.append(t)

    # AI enrichment: infer real sector/products/inputs/customers from the name.
    if ai.is_available() and new_targets:
        for t in new_targets:
            data = ai.enrich_company(t.name, t.description)
            if data:
                t.sector = data.get("sector") or t.sector
                t.products = data.get("products") or t.products
                t.raw_materials = data.get("raw_materials") or t.raw_materials
                t.customers = data.get("customers") or t.customers
    db.commit()

    if rematch and new_targets:
        targets = db.query(Target).all()
        for b in db.query(Buyer).all():
            match_buyer_against_targets(db, b, targets, use_ai=True)

    prune_stale(db, settings.retention_days)
    return len(companies), len(new_targets)


# ---- retention ----
_MON = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _parse_date(s: str | None):
    from datetime import date as _date
    if not s:
        return None
    s = s.strip()
    m = re.match(r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})", s)        # DD-MM-YYYY
    if m:
        try:
            return _date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    m = re.match(r"(\d{1,2})\s+([A-Za-z]{3,})\s+(\d{4})", s)      # DD Mon YYYY
    if m and m.group(2)[:3].lower() in _MON:
        try:
            return _date(int(m.group(3)), _MON[m.group(2)[:3].lower()], int(m.group(1)))
        except ValueError:
            return None
    return None


def prune_stale(db: Session, retention_days: int) -> int:
    """Delete live (non-seed) targets that are BOTH announced > retention_days ago
    AND no longer active (claims & Form-G windows closed). Seed showcase is kept.
    Returns the number pruned."""
    from datetime import date, timedelta
    from ..models import MatchResult

    today = date.today()
    cutoff = today - timedelta(days=retention_days)
    pruned = 0
    for t in db.query(Target).all():
        if (t.source_ref or "").startswith("seed-"):
            continue
        admitted = _parse_date(t.admit) or _parse_date(t.announcement_date)
        if admitted and admitted >= cutoff:
            continue  # recent -> keep
        claims = _parse_date(t.claims_by)
        formg = _parse_date(t.form_g_by)
        active = (claims and claims >= today) or (formg and formg >= today)
        if active:
            continue  # window still open -> keep
        if admitted is None:
            continue  # unknown date -> keep (don't delete uncertain)
        db.query(MatchResult).filter(MatchResult.target_id == t.id).delete()
        db.delete(t)
        pruned += 1
    if pruned:
        db.commit()
    return pruned
