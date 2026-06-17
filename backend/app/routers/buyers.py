"""Buyer roster — CRUD + Excel/CSV import. Scoped to the logged-in user."""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..database import get_db
from ..importer import parse_upload
from ..models import Buyer, User
from ..schemas import BuyerCreate, BuyerOut
from ..security import get_current_user

router = APIRouter(prefix="/api/buyers", tags=["buyers"])


def _owned(db: Session, buyer_id: int, user: User) -> Buyer:
    b = db.get(Buyer, buyer_id)
    if not b or (b.owner_id != user.id and not user.is_admin):
        raise HTTPException(404, "Buyer not found")
    return b


@router.get("", response_model=list[BuyerOut])
def list_buyers(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Buyer).filter(Buyer.owner_id == user.id).order_by(Buyer.name).all()


@router.post("", response_model=BuyerOut)
def create_buyer(payload: BuyerCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    b = Buyer(owner_id=user.id, **payload.model_dump())
    db.add(b)
    db.commit()
    db.refresh(b)
    return b


@router.put("/{buyer_id}", response_model=BuyerOut)
def update_buyer(buyer_id: int, payload: BuyerCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    b = _owned(db, buyer_id, user)
    for k, v in payload.model_dump().items():
        setattr(b, k, v)
    db.commit()
    db.refresh(b)
    return b


@router.delete("/{buyer_id}")
def delete_buyer(buyer_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    b = _owned(db, buyer_id, user)
    db.delete(b)
    db.commit()
    return {"deleted": buyer_id}


@router.post("/import")
async def import_buyers(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    content = await file.read()
    parsed = parse_upload(file.filename or "upload.xlsx", content)
    if not parsed:
        raise HTTPException(400, "No valid buyer rows found. Need at least a 'Name' column.")
    created = 0
    for p in parsed:
        db.add(Buyer(owner_id=user.id, **p.model_dump()))
        created += 1
    db.commit()
    return {"imported": created, "rows_seen": len(parsed)}
