"""The premium feature: run acquisition-fit analysis for a buyer (paywalled)."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..matching import match_buyer_against_targets
from ..models import Buyer, Target, User
from ..schemas import MatchWithTarget, TargetOut
from ..security import require_paid

router = APIRouter(prefix="/api/match", tags=["matching"])


@router.post("/buyer/{buyer_id}", response_model=list[MatchWithTarget])
def run_match(
    buyer_id: int,
    min_score: float = Query(25.0, ge=0, le=100),
    user: User = Depends(require_paid),
    db: Session = Depends(get_db),
):
    buyer = db.get(Buyer, buyer_id)
    if not buyer or (buyer.owner_id != user.id and not user.is_admin):
        raise HTTPException(404, "Buyer not found")

    targets = db.query(Target).all()
    if not targets:
        raise HTTPException(400, "No IBC targets loaded yet. Refresh the feed first.")

    candidates = match_buyer_against_targets(db, buyer, targets, use_ai=True)
    out = [
        MatchWithTarget(
            id=0, buyer_id=buyer.id, target_id=c.target.id,
            synergy_type=c.synergy_type, score=c.score, rationale=c.rationale,
            engine=c.engine, target=TargetOut.model_validate(c.target),
        )
        for c in candidates if c.score >= min_score
    ]
    return out
