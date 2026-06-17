"""Database models.

Target   — a distressed company in the IBC process (scraped from the source site).
Buyer    — a cash-rich acquirer profile (a subscriber's own company, or one your
           firm maintains). The thing we match Targets against.
User     — an account. tier = "free" | "paid" gates the AI feasibility engine.
MatchResult — a cached (buyer, target) synergy verdict produced by the engine.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255), default="")
    tier: Mapped[str] = mapped_column(String(20), default="free")  # free | paid
    is_admin: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    buyers: Mapped[list["Buyer"]] = relationship(back_populates="owner", cascade="all, delete-orphan")


class Target(Base):
    """A company in / entering the Insolvency & Bankruptcy process."""
    __tablename__ = "targets"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(500), index=True)
    sector: Mapped[str] = mapped_column(String(255), default="")
    products: Mapped[str] = mapped_column(Text, default="")          # what it makes/sells
    raw_materials: Mapped[str] = mapped_column(Text, default="")     # what it consumes
    customers: Mapped[str] = mapped_column(Text, default="")         # who it sells to
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(100), default="")     # CIRP / Liquidation / Auction
    process_type: Mapped[str] = mapped_column(String(100), default="")
    resolution_professional: Mapped[str] = mapped_column(String(255), default="")
    location: Mapped[str] = mapped_column(String(255), default="")
    announcement_date: Mapped[str] = mapped_column(String(50), default="")
    source_url: Mapped[str] = mapped_column(String(1000), default="")
    source_ref: Mapped[str] = mapped_column(String(255), default="", index=True)  # de-dup key

    # --- IBC process / Form-G tracking (Jarvis desk) ---
    is_liq: Mapped[bool] = mapped_column(default=False)               # liquidation vs CIRP
    stage_label: Mapped[str] = mapped_column(String(120), default="")  # e.g. "Corporate Insolvency Resolution Process"
    stage_class: Mapped[str] = mapped_column(String(20), default="cirp")  # cirp | liq | formg
    applicant: Mapped[str] = mapped_column(String(500), default="")   # lead applicant / creditor
    admit: Mapped[str] = mapped_column(String(50), default="")        # admission date (display)
    claims_by: Mapped[str] = mapped_column(String(50), default="")    # claims deadline (display)
    claims_days: Mapped[int | None] = mapped_column(Integer, nullable=True)  # days to claims (snapshot)
    form_g_by: Mapped[str | None] = mapped_column(String(50), nullable=True)  # expected Form G (~75d)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (UniqueConstraint("source_ref", name="uq_target_source_ref"),)


class Buyer(Base):
    """A potential acquirer profile we match distressed Targets against."""
    __tablename__ = "buyers"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(500), index=True)
    sector: Mapped[str] = mapped_column(String(255), default="")
    products: Mapped[str] = mapped_column(Text, default="")            # what the buyer makes
    raw_materials_needed: Mapped[str] = mapped_column(Text, default="")  # backward-integration targets
    customers_served: Mapped[str] = mapped_column(Text, default="")     # forward-integration targets
    acquisition_thesis: Mapped[str] = mapped_column(Text, default="")   # free-text mandate
    surplus_cash_inr_cr: Mapped[float] = mapped_column(Float, default=0.0)
    geography_pref: Mapped[str] = mapped_column(String(255), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    owner: Mapped["User"] = relationship(back_populates="buyers")


class Deal(Base):
    """A closed KCM mandate — the firm's track record.

    Public visitors see the count + total FMV (social proof); paid users see the
    companies involved. Admin-maintained ('update on his will')."""
    __tablename__ = "deals"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_name: Mapped[str] = mapped_column(String(500))           # the acquirer KCM advised
    target_name: Mapped[str] = mapped_column(String(500), default="")  # the distressed asset acquired
    service_type: Mapped[str] = mapped_column(String(120), default="Acquisition & structuring")
    fmv_inr_cr: Mapped[float] = mapped_column(Float, default=0.0)    # FMV of benefit to client (₹ cr)
    closed_on: Mapped[str] = mapped_column(String(50), default="")   # display date
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class MatchResult(Base):
    """A scored synergy verdict between one Buyer and one Target."""
    __tablename__ = "match_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    buyer_id: Mapped[int] = mapped_column(ForeignKey("buyers.id", ondelete="CASCADE"), index=True)
    target_id: Mapped[int] = mapped_column(ForeignKey("targets.id", ondelete="CASCADE"), index=True)
    synergy_type: Mapped[str] = mapped_column(String(50), default="")   # backward|forward|horizontal|none
    score: Mapped[float] = mapped_column(Float, default=0.0)            # 0-100 feasibility
    rationale: Mapped[str] = mapped_column(Text, default="")
    engine: Mapped[str] = mapped_column(String(20), default="rules")    # rules | ai

    # --- Jarvis match-card gates ---
    matched_keywords: Mapped[str] = mapped_column(Text, default="")     # comma-joined overlap tokens
    reach: Mapped[str] = mapped_column(Text, default="")               # KCM reachability note
    eligibility_29a: Mapped[str] = mapped_column(Text, default="")     # Sec 29A / distress caveat
    na_class: Mapped[str] = mapped_column(String(20), default="g-warn")  # gate colour for 29A
    confidence: Mapped[str] = mapped_column(String(20), default="MEDIUM")  # HIGH|MEDIUM|LOW
    conf_class: Mapped[str] = mapped_column(String(20), default="g-warn")  # gate colour for data conf
    bar_w: Mapped[float] = mapped_column(Float, default=0.0)           # score bar width (0-100)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (UniqueConstraint("buyer_id", "target_id", name="uq_match_pair"),)
