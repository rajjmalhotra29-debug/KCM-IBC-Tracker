"""Pydantic request/response schemas."""
from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------- Auth ----------
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    full_name: str = ""


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    full_name: str
    tier: str
    is_admin: bool


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- Target ----------
class TargetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    sector: str
    products: str
    raw_materials: str
    customers: str
    description: str
    status: str
    process_type: str
    resolution_professional: str
    location: str
    announcement_date: str
    source_url: str
    is_liq: bool = False
    stage_label: str = ""
    stage_class: str = "cirp"
    applicant: str = ""
    admit: str = ""
    claims_by: str = ""
    claims_days: int | None = None
    form_g_by: str | None = None
    pa_pdf: str = ""
    profile: dict | None = None     # web-researched company profile (enrich.py)


# ---------- Buyer ----------
class BuyerBase(BaseModel):
    name: str
    sector: str = ""
    products: str = ""
    raw_materials_needed: str = ""
    customers_served: str = ""
    acquisition_thesis: str = ""
    surplus_cash_inr_cr: float = 0.0
    geography_pref: str = ""
    notes: str = ""


class BuyerCreate(BuyerBase):
    pass


class BuyerOut(BuyerBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


# ---------- Matching ----------
class MatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    buyer_id: int
    target_id: int
    synergy_type: str
    score: float
    rationale: str
    engine: str
    matched_keywords: str = ""
    reach: str = ""
    eligibility_29a: str = ""
    na_class: str = "g-warn"
    confidence: str = "MEDIUM"
    conf_class: str = "g-warn"
    bar_w: float = 0.0


class MatchWithTarget(MatchOut):
    target: TargetOut


# A match as shown on a Jarvis opportunity card (client = buyer name).
class MatchCard(BaseModel):
    client: str
    synergy_type: str
    score: float
    rationale: str
    matched_keywords: str = ""
    reach: str = ""
    eligibility_29a: str = ""
    na_class: str = "g-warn"
    confidence: str = "MEDIUM"
    conf_class: str = "g-warn"
    bar_w: float = 0.0
    engine: str = "rules"


# One opportunity card: a Target + its ranked matches (locked for free tier).
class OpportunityCard(BaseModel):
    target: TargetOut
    matches: list[MatchCard] = []
    match_count: int = 0
    locked: bool = False


# ---------- Deals / track record ----------
class DealBase(BaseModel):
    client_name: str
    target_name: str = ""
    service_type: str = "Acquisition & structuring"
    fmv_inr_cr: float = 0.0
    closed_on: str = ""
    notes: str = ""


class DealCreate(DealBase):
    pass


class DealOut(DealBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


class TrackRecord(BaseModel):
    deals_closed: int = 0
    value_fmv_inr_cr: float = 0.0
    deals: list[DealOut] = []     # populated only when the viewer may see companies
    locked: bool = False          # True when company details are gated


class Dashboard(BaseModel):
    generated: str
    source_url: str
    adapter: str
    ai_enabled: bool
    tier: str
    mode: str = "open"            # open | freemium
    brand: str = "kcm"            # kcm | jarvis
    contact_email: str = ""
    track_record: TrackRecord = TrackRecord()
    opportunities: list[OpportunityCard]


class ExtractResult(BaseModel):
    source_url: str
    adapter: str
    found: int
    new: int
    message: str
