"""Seed the database from the Jarvis desk snapshot (seed_data.json).

Creates:
  - admin@ibc.local (admin, paid) — owns the firm's "house book" of buyers.
  - buyer@ibc.local (paid)        — a demo subscriber for the per-buyer flow.
  - one Target per distressed company (with Form G / claims / applicant info),
  - one Buyer per distinct matched client (the firm's client master),
  - one MatchResult per (company, client) match — the house intelligence the
    dashboard renders. Idempotent.

Run:  python -m app.seed
"""
import hashlib
import json
import re
from pathlib import Path

from .database import SessionLocal, init_db
from .models import Buyer, Deal, MatchResult, Target, User
from .security import hash_password

# Illustrative closed mandates (track record). Admin edits these in-app.
DEMO_DEALS = [
    dict(client_name="Bharat Tyre Manufacturing Ltd", target_name="Vulcan Speciality Chemicals Ltd",
         service_type="Acquisition & backward integration", fmv_inr_cr=185.0, closed_on="Mar 2026",
         notes="Secured captive LSD-chemical supply via CIRP resolution."),
    dict(client_name="Cadila Pharmaceuticals Limited", target_name="Martina Bio Genics Pvt Ltd",
         service_type="Acquisition & structuring", fmv_inr_cr=240.0, closed_on="Feb 2026",
         notes="API/KSM capacity added through liquidation going-concern sale."),
    dict(client_name="Best Paper Mills Private Limited", target_name="Danalakshmi Paper Mills Pvt Ltd",
         service_type="Acquisition & restructuring", fmv_inr_cr=96.5, closed_on="Jan 2026",
         notes="Kraft-paper tonnage consolidation."),
    dict(client_name="Asian Granito India Limited", target_name="New Pearl Vitrified Pvt Ltd",
         service_type="Structuring & advisory", fmv_inr_cr=130.0, closed_on="Dec 2025",
         notes="Vitrified-tile kiln capacity, Morbi cluster."),
]

DATA_FILE = Path(__file__).resolve().parent / "seed_data.json"
IBBI_URL = "https://www.ibbi.gov.in/en/public-announcement"

ADMIN_EMAIL, ADMIN_PASS = "admin@ibc.local", "admin123"
DEMO_EMAIL, DEMO_PASS = "buyer@ibc.local", "buyer123"

_SYN_ORDER = ["backward", "forward", "horizontal"]


def _infer_synergy(syn: str) -> str:
    """Pick the dominant integration type from the rationale text."""
    low = (syn or "").lower()
    first = None, len(low) + 1
    for t in _SYN_ORDER:
        i = low.find(t)
        if i != -1 and i < first[1]:
            first = t, i
    return first[0] or "horizontal"


def _sector_from_keywords(matches: list[dict]) -> str:
    kws = []
    for m in matches:
        kws += m.get("matched", [])
    # crude but useful: show the top distinct keywords as a sector hint
    seen, out = set(), []
    for k in kws:
        if k not in seen:
            seen.add(k); out.append(k)
    return ", ".join(out[:4])


def _ref(company: str) -> str:
    return "seed-" + hashlib.sha1(company.encode()).hexdigest()[:16]


def run():
    init_db()
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    opps = data.get("opportunities", [])

    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.email == ADMIN_EMAIL).first()
        if not admin:
            admin = User(email=ADMIN_EMAIL, hashed_password=hash_password(ADMIN_PASS),
                         full_name="KCM Origination Desk", tier="paid", is_admin=True)
            db.add(admin)
        if not db.query(User).filter(User.email == DEMO_EMAIL).first():
            db.add(User(email=DEMO_EMAIL, hashed_password=hash_password(DEMO_PASS),
                        full_name="Demo Subscriber", tier="paid"))
        db.commit(); db.refresh(admin)

        # buyers (house book) keyed by client name
        buyers: dict[str, Buyer] = {}

        def get_buyer(name: str, sector: str, thesis: str) -> Buyer:
            if name in buyers:
                return buyers[name]
            b = db.query(Buyer).filter(Buyer.name == name, Buyer.owner_id == admin.id).first()
            if not b:
                b = Buyer(owner_id=admin.id, name=name, sector=sector,
                          acquisition_thesis=thesis[:400])
                db.add(b); db.flush()
            buyers[name] = b
            return b

        for o in opps:
            ref = _ref(o["company"])
            t = db.query(Target).filter(Target.source_ref == ref).first()
            sector = _sector_from_keywords(o.get("matches", []))
            if not t:
                t = Target(
                    name=o["company"], source_ref=ref, source_url=IBBI_URL,
                    sector=sector, status=o.get("stageLabel", ""),
                    process_type=o.get("stageLabel", ""),
                    resolution_professional=o.get("rp", ""),
                    announcement_date=o.get("admit", ""),
                    is_liq=bool(o.get("isLiq")),
                    stage_label=o.get("stageLabel", ""),
                    stage_class=o.get("stageClass", "cirp"),
                    applicant=o.get("applicant", ""),
                    admit=o.get("admit", ""),
                    claims_by=o.get("claimsBy", ""),
                    claims_days=o.get("claimsDays"),
                    form_g_by=o.get("formgBy"),
                )
                db.add(t); db.flush()

            for m in o.get("matches", []):
                b = get_buyer(m["client"], sector, m.get("syn", ""))
                exists = (db.query(MatchResult)
                          .filter(MatchResult.buyer_id == b.id, MatchResult.target_id == t.id)
                          .first())
                if exists:
                    continue
                db.add(MatchResult(
                    buyer_id=b.id, target_id=t.id,
                    synergy_type=_infer_synergy(m.get("syn", "")),
                    score=float(m.get("score", 0)),
                    rationale=m.get("syn", ""),
                    engine="rules",
                    matched_keywords=", ".join(m.get("matched", [])),
                    reach=m.get("reach", ""),
                    eligibility_29a=m.get("na", "Verify"),
                    na_class=m.get("naClass", "g-warn"),
                    confidence=m.get("conf", "MEDIUM"),
                    conf_class=m.get("confClass", "g-warn"),
                    bar_w=float(m.get("barW", m.get("score", 0))),
                ))
        db.commit()

        # deals / track record
        if db.query(Deal).count() == 0:
            for d in DEMO_DEALS:
                db.add(Deal(**d))
            db.commit()

        print("Seed complete (Jarvis snapshot).")
        print(f"  Admin (desk) : {ADMIN_EMAIL} / {ADMIN_PASS}")
        print(f"  Demo paid    : {DEMO_EMAIL} / {DEMO_PASS}")
        print(f"  Targets: {db.query(Target).count()}  "
              f"Buyers: {db.query(Buyer).count()}  "
              f"Matches: {db.query(MatchResult).count()}")
    finally:
        db.close()


if __name__ == "__main__":
    run()
