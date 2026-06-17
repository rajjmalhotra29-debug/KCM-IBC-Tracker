"""Freemium upgrade flow.

When Razorpay keys are configured (PAYMENTS_ENABLED + keys), /checkout creates a
real order; a verified webhook/confirm flips the user to the paid tier. Until
then it runs in 'demo unlock' mode so the premium path is testable end-to-end.
"""
import hashlib
import hmac

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import User
from ..schemas import UserOut
from ..security import get_current_user

router = APIRouter(prefix="/api/billing", tags=["billing"])


class CheckoutOut(BaseModel):
    mode: str               # "razorpay" | "demo"
    amount_inr: int
    order_id: str | None = None
    razorpay_key_id: str | None = None
    message: str


class ConfirmIn(BaseModel):
    order_id: str | None = None
    payment_id: str | None = None
    signature: str | None = None


@router.get("/plan")
def plan():
    return {
        "price_inr": settings.subscription_price_inr,
        "payments_enabled": settings.payments_enabled and bool(settings.razorpay_key_id),
        "features_free": ["Browse live IBC distressed-company feed", "Search & filter targets"],
        "features_paid": [
            "AI acquisition-fit analysis for your company",
            "Backward / forward / horizontal synergy scoring",
            "Ranked target shortlist with rationale",
            "Unlimited buyer profiles + Excel import",
        ],
    }


@router.post("/checkout", response_model=CheckoutOut)
def checkout(user: User = Depends(get_current_user)):
    amount = settings.subscription_price_inr
    if settings.payments_enabled and settings.razorpay_key_id and settings.razorpay_key_secret:
        try:
            import razorpay  # optional dep; only needed when going live
            client = razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))
            order = client.order.create({
                "amount": amount * 100, "currency": "INR", "payment_capture": 1,
                "notes": {"user_id": str(user.id), "email": user.email},
            })
            return CheckoutOut(
                mode="razorpay", amount_inr=amount, order_id=order["id"],
                razorpay_key_id=settings.razorpay_key_id,
                message="Complete payment in the Razorpay popup.",
            )
        except ImportError:
            raise HTTPException(500, "razorpay package not installed; run pip install razorpay")
    # demo mode
    return CheckoutOut(
        mode="demo", amount_inr=amount, order_id=None, razorpay_key_id=None,
        message="Payments not configured — demo unlock available for testing.",
    )


@router.post("/confirm", response_model=UserOut)
def confirm(payload: ConfirmIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    live = settings.payments_enabled and settings.razorpay_key_secret
    if live:
        if not (payload.order_id and payload.payment_id and payload.signature):
            raise HTTPException(400, "Missing payment verification fields")
        expected = hmac.new(
            settings.razorpay_key_secret.encode(),
            f"{payload.order_id}|{payload.payment_id}".encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, payload.signature):
            raise HTTPException(400, "Payment signature verification failed")
    # mark paid (demo: unconditional; live: only after signature check passes)
    user.tier = "paid"
    db.commit()
    db.refresh(user)
    return user
