"""The Jarvis desk dashboard — opportunities + their ranked client matches.

Matches are the firm's "house book" intelligence (MatchResults against the
admin-owned buyer roster). They are the PREMIUM product: free / anonymous
visitors see every opportunity card in full (process, Form G tracker, financial
snapshot) but the client matches are locked until they log in on a paid tier.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..matching import match_buyer_against_targets
from ..models import Buyer, MatchResult, Target, User
from ..schemas import Dashboard, MatchCard, OpportunityCard, TargetOut
from ..security import get_current_user_optional, require_admin
from .deals import build_track_record

router = APIRouter(prefix="/api", tags=["dashboard"])

PREVIEW_LOCKED = 3  # how many matches a locked card advertises (count only)


def _is_paid(user: User | None) -> bool:
    # Open mode = everything unlocked for everyone.
    if settings.is_open:
        return True
    return bool(user and (user.tier == "paid" or user.is_admin))


@router.get("/dashboard", response_model=Dashboard)
def dashboard(
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    return build_dashboard(db, user)


def build_dashboard(db: Session, user: User | None) -> Dashboard:
    """Assemble the full dashboard payload. Used by the live route AND the
    static-site build (app/build_site.py)."""
    paid = _is_paid(user)
    targets = db.query(Target).order_by(Target.created_at.desc()).all()

    # Pull all house matches once, grouped by target.
    rows = (
        db.query(MatchResult, Buyer.name)
        .join(Buyer, Buyer.id == MatchResult.buyer_id)
        .order_by(MatchResult.score.desc())
        .all()
    )
    by_target: dict[int, list[tuple[MatchResult, str]]] = {}
    for mr, bname in rows:
        by_target.setdefault(mr.target_id, []).append((mr, bname))

    cards: list[OpportunityCard] = []
    for t in targets:
        mlist = by_target.get(t.id, [])
        count = len(mlist)
        if paid:
            matches = [
                MatchCard(
                    client=bname, synergy_type=mr.synergy_type, score=mr.score,
                    rationale=mr.rationale, matched_keywords=mr.matched_keywords,
                    reach=mr.reach, eligibility_29a=mr.eligibility_29a,
                    na_class=mr.na_class, confidence=mr.confidence,
                    conf_class=mr.conf_class, bar_w=mr.bar_w or mr.score, engine=mr.engine,
                )
                for mr, bname in mlist
            ]
            locked = False
        else:
            matches = []
            locked = count > 0
        cards.append(OpportunityCard(
            target=TargetOut.model_validate(t),
            matches=matches, match_count=count, locked=locked,
        ))

    ist_now = datetime.now(timezone(timedelta(hours=5, minutes=30)))   # India time
    return Dashboard(
        generated=ist_now.strftime("%d %b %Y, %H:%M IST"),
        source_url=settings.source_url, adapter=settings.source_adapter,
        ai_enabled=settings.ai_enabled,
        tier=("open" if settings.is_open else (user.tier if user else "anonymous")),
        mode=settings.access_mode,
        brand=settings.brand,
        contact_email=settings.contact_email,
        track_record=build_track_record(db, user),
        opportunities=cards,
    )


@router.post("/match/run-all")
def run_all(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Recompute the house book: every admin-owned buyer against every target."""
    targets = db.query(Target).all()
    buyers = db.query(Buyer).all()
    total = 0
    for b in buyers:
        cands = match_buyer_against_targets(db, b, targets, use_ai=True)
        total += sum(1 for c in cands if c.score > 0)
    return {"buyers": len(buyers), "targets": len(targets), "matches": total}
