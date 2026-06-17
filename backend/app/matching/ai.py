"""AI ranker — Anthropic-powered semantic synergy analysis.

Activates only when ANTHROPIC_API_KEY is set. Given a buyer and a shortlist of
targets (already pre-filtered by rules), it reasons about real supply-chain fit
— including indirect / 'raw-material-of-a-raw-material' and near-match customer
relationships that keyword rules miss — and returns a calibrated feasibility
score + rationale per target.
"""
from __future__ import annotations

import json

from ..config import settings
from ..models import Buyer, Target

_SYSTEM = """You are an M&A strategy analyst specialising in distressed-asset \
acquisitions under India's Insolvency & Bankruptcy Code (IBC). For a given \
acquirer (Buyer) and a distressed Target company, judge how strategically fit \
the Target is for the Buyer to acquire, focusing on supply-chain synergy:
- backward: Target supplies a raw material / input the Buyer needs.
- forward: Target is a natural customer / downstream user of the Buyer's output.
- horizontal: Target is in the Buyer's own line (consolidation, capacity, share).
- none: no meaningful strategic fit.

Reason about INDIRECT links too (e.g. Target makes a chemical that is an input to \
a component the Buyer buys). Be commercially realistic and concise.

Return STRICT JSON only, no prose:
{"synergy_type": "...", "score": 0-100, "rationale": "1-3 sentences"}
score = overall acquisition feasibility/attractiveness for THIS buyer."""


def _buyer_blurb(b: Buyer) -> str:
    return (
        f"Buyer: {b.name}\nSector: {b.sector}\nMakes/sells: {b.products}\n"
        f"Raw materials it needs: {b.raw_materials_needed}\n"
        f"Customers it serves: {b.customers_served}\n"
        f"Acquisition thesis: {b.acquisition_thesis}\n"
        f"Surplus cash (INR cr): {b.surplus_cash_inr_cr}\n"
        f"Geography preference: {b.geography_pref}"
    )


def _target_blurb(t: Target) -> str:
    return (
        f"Target: {t.name}\nSector: {t.sector}\nMakes/sells: {t.products}\n"
        f"Consumes (raw materials): {t.raw_materials}\nSells to: {t.customers}\n"
        f"IBC status: {t.status} {t.process_type}\nLocation: {t.location}\n"
        f"Notes: {t.description}"
    )


def is_available() -> bool:
    return settings.ai_enabled


_ENRICH_SYSTEM = """You are an analyst profiling a distressed Indian company from \
its IBC public announcement. From the company name (and any notes), infer its \
likely business so it can be matched to acquirers. Be specific but honest about \
uncertainty; if the name is generic, give your best inference.

Return STRICT JSON only:
{"sector": "...", "products": "what it makes/sells", "raw_materials": "key inputs it consumes", "customers": "who it sells to"}
Keep each value short (a few comma-separated items)."""


def enrich_company(name: str, description: str = "") -> dict | None:
    """Infer sector/products/raw_materials/customers for a scraped target.
    Returns the dict, or None if AI unavailable/failed. Makes matching far
    sharper than name-keyword inference."""
    if not settings.ai_enabled:
        return None
    try:
        import anthropic
    except ImportError:
        return None
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    user = f"Company: {name}\nIBC announcement notes: {description[:400]}\n\nProfile it and return the JSON."
    try:
        msg = client.messages.create(
            model=settings.ai_model, max_tokens=300,
            system=_ENRICH_SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in msg.content if b.type == "text")
        data = _parse_json(text)
        if not data:
            return None
        return {k: str(data.get(k, "")) for k in ("sector", "products", "raw_materials", "customers")}
    except Exception:
        return None


def score_pair_ai(buyer: Buyer, target: Target) -> dict | None:
    """Return {'synergy_type','score','rationale'} or None if AI unavailable/failed."""
    if not settings.ai_enabled:
        return None
    try:
        import anthropic
    except ImportError:
        return None

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    user = (
        f"{_buyer_blurb(buyer)}\n\n---\n\n{_target_blurb(target)}\n\n"
        "Assess the acquisition fit and return the JSON."
    )
    try:
        msg = client.messages.create(
            model=settings.ai_model,
            max_tokens=400,
            system=_SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(block.text for block in msg.content if block.type == "text").strip()
        data = _parse_json(text)
        if not data:
            return None
        data["score"] = max(0.0, min(100.0, float(data.get("score", 0))))
        data.setdefault("synergy_type", "none")
        data.setdefault("rationale", "")
        return data
    except Exception:
        return None


def _parse_json(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[-1] if "\n" in text else text
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
