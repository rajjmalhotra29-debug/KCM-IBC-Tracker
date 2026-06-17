"""Rule-based pre-filter + cheap scorer.

This is the free first pass of the hybrid engine. It looks for token overlap
between a Buyer's supply-chain needs and a Target's business, classifying the
relationship as backward / forward / horizontal integration. Cheap, explainable,
and runs with no API key — good enough to shortlist before the AI ranker.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..models import Buyer, Target

_STOP = {
    "the", "and", "for", "ltd", "limited", "pvt", "private", "llp", "of", "co",
    "company", "india", "manufacturer", "manufacturing", "products", "product",
    "services", "service", "&", "-", "inc", "corp", "industries", "industry",
}


def _tokens(*texts: str) -> set[str]:
    out: set[str] = set()
    for t in texts:
        for w in re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", (t or "").lower()):
            if w not in _STOP:
                out.add(w)
    return out


@dataclass
class RuleVerdict:
    synergy_type: str  # backward | forward | horizontal | none
    score: float       # 0-100
    rationale: str
    overlap: set[str]


def _overlap_score(a: set[str], b: set[str]) -> tuple[float, set[str]]:
    if not a or not b:
        return 0.0, set()
    common = a & b
    if not common:
        return 0.0, set()
    # Jaccard-ish, scaled; capped so rules never fully saturate (AI refines).
    frac = len(common) / min(len(a), len(b))
    return min(85.0, 25.0 + frac * 70.0), common


def score_pair(buyer: Buyer, target: Target) -> RuleVerdict:
    target_make = _tokens(target.products, target.sector, target.name, target.description)
    target_consume = _tokens(target.raw_materials)
    target_sells_to = _tokens(target.customers)

    buyer_needs = _tokens(buyer.raw_materials_needed)
    buyer_make = _tokens(buyer.products, buyer.sector)
    buyer_sells_to = _tokens(buyer.customers_served)

    candidates: list[RuleVerdict] = []

    # Backward integration: target MAKES what buyer NEEDS.
    s, ov = _overlap_score(buyer_needs, target_make)
    if s:
        candidates.append(RuleVerdict(
            "backward", s,
            f"Target appears to produce inputs the buyer consumes ({_fmt(ov)}). "
            f"Acquiring secures backward integration / raw-material supply.",
            ov,
        ))

    # Forward integration: target IS a customer for what buyer MAKES.
    s, ov = _overlap_score(buyer_make, target_consume)
    if s:
        candidates.append(RuleVerdict(
            "forward", s,
            f"Target consumes what the buyer produces ({_fmt(ov)}). "
            f"Acquiring captures a downstream customer (forward integration).",
            ov,
        ))

    # Horizontal: same line of business.
    s, ov = _overlap_score(buyer_make, target_make)
    if s:
        candidates.append(RuleVerdict(
            "horizontal", max(20.0, s - 10.0),
            f"Target operates in the buyer's own line ({_fmt(ov)}). "
            f"Consolidation play — capacity, market share, distressed valuation.",
            ov,
        ))

    if not candidates:
        return RuleVerdict("none", 0.0, "No obvious supply-chain overlap from rules.", set())
    return max(candidates, key=lambda c: c.score)


def _fmt(tokens: set[str]) -> str:
    return ", ".join(sorted(tokens)[:6])
