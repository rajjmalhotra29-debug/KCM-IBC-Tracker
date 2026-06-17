"""Track record — KCM's closed mandates.

Public: count + total FMV (social proof). Paid / open mode: the companies too.
Admin maintains the list ('update on his will')."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Deal, User
from ..schemas import DealCreate, DealOut, TrackRecord
from ..security import get_current_user_optional, require_admin

router = APIRouter(prefix="/api/deals", tags=["deals"])


def viewer_may_see_companies(user: User | None) -> bool:
    if settings.is_open:
        return True
    return bool(user and (user.tier == "paid" or user.is_admin))


def build_track_record(db: Session, user: User | None) -> TrackRecord:
    count = db.query(func.count(Deal.id)).scalar() or 0
    total = db.query(func.coalesce(func.sum(Deal.fmv_inr_cr), 0.0)).scalar() or 0.0
    tr = TrackRecord(deals_closed=int(count), value_fmv_inr_cr=round(float(total), 2))
    if viewer_may_see_companies(user):
        tr.deals = [DealOut.model_validate(d) for d in
                    db.query(Deal).order_by(Deal.created_at.desc()).all()]
        tr.locked = False
    else:
        tr.deals = []
        tr.locked = count > 0
    return tr


@router.get("", response_model=TrackRecord)
def list_deals(user: User | None = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    return build_track_record(db, user)


@router.post("", response_model=DealOut)
def create_deal(payload: DealCreate, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    d = Deal(**payload.model_dump())
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


@router.put("/{deal_id}", response_model=DealOut)
def update_deal(deal_id: int, payload: DealCreate, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    d = db.get(Deal, deal_id)
    if not d:
        raise HTTPException(404, "Deal not found")
    for k, v in payload.model_dump().items():
        setattr(d, k, v)
    db.commit()
    db.refresh(d)
    return d


@router.delete("/{deal_id}")
def delete_deal(deal_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    d = db.get(Deal, deal_id)
    if not d:
        raise HTTPException(404, "Deal not found")
    db.delete(d)
    db.commit()
    return {"deleted": deal_id}
