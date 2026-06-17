"""Hybrid orchestrator: rules pre-filter -> AI ranker -> persisted MatchResults.

1. Score every (buyer, target) pair cheaply with rules.
2. Keep the survivors above RULE_FLOOR (or top-K if AI is on).
3. If AI is available, re-score the survivors semantically; otherwise keep rules.
4. Upsert results into match_results and return them sorted by score.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..models import Buyer, MatchResult, Target
from . import ai, rules

RULE_FLOOR = 25.0   # below this, rules say "no meaningful link"
AI_SHORTLIST = 15    # max targets sent to the AI per buyer (cost guard)


def _confidence(score: float) -> tuple[str, str]:
    if score >= 60:
        return "HIGH", "g-ok"
    if score >= 35:
        return "MEDIUM", "g-warn"
    return "LOW", "g-bad"


@dataclass
class Candidate:
    target: Target
    synergy_type: str
    score: float
    rationale: str
    engine: str
    matched_keywords: str = ""
    reach: str = "Indian promoter — verify reachability"
    eligibility_29a: str = "Verify; no public distress indicators found."
    na_class: str = "g-warn"
    confidence: str = "MEDIUM"
    conf_class: str = "g-warn"
    bar_w: float = 0.0


def match_buyer_against_targets(
    db: Session, buyer: Buyer, targets: list[Target], use_ai: bool = True
) -> list[Candidate]:
    # 1) rules pass
    scored: list[tuple[Target, rules.RuleVerdict]] = []
    for t in targets:
        v = rules.score_pair(buyer, t)
        if v.score >= RULE_FLOOR:
            scored.append((t, v))
    scored.sort(key=lambda x: x[1].score, reverse=True)

    # 2) AI refinement on the shortlist
    ai_on = use_ai and ai.is_available()
    candidates: list[Candidate] = []
    for i, (t, v) in enumerate(scored):
        kw = ", ".join(sorted(v.overlap)[:8])
        if ai_on and i < AI_SHORTLIST:
            res = ai.score_pair_ai(buyer, t)
            if res:
                conf, conf_cls = _confidence(res["score"])
                candidates.append(Candidate(
                    target=t,
                    synergy_type=res["synergy_type"],
                    score=res["score"],
                    rationale=res["rationale"],
                    engine="ai",
                    matched_keywords=kw,
                    confidence=conf, conf_class=conf_cls,
                    bar_w=res["score"],
                ))
                continue
        conf, conf_cls = _confidence(v.score)
        candidates.append(Candidate(
            target=t, synergy_type=v.synergy_type, score=v.score,
            rationale=v.rationale, engine="rules",
            matched_keywords=kw, confidence=conf, conf_class=conf_cls,
            bar_w=v.score,
        ))

    candidates.sort(key=lambda c: c.score, reverse=True)
    _persist(db, buyer, candidates)
    return candidates


def _persist(db: Session, buyer: Buyer, candidates: list[Candidate]) -> None:
    for c in candidates:
        row = (
            db.query(MatchResult)
            .filter(MatchResult.buyer_id == buyer.id, MatchResult.target_id == c.target.id)
            .first()
        )
        if row is None:
            row = MatchResult(buyer_id=buyer.id, target_id=c.target.id)
            db.add(row)
        row.synergy_type = c.synergy_type
        row.score = c.score
        row.rationale = c.rationale
        row.engine = c.engine
        row.matched_keywords = c.matched_keywords
        row.reach = c.reach
        row.eligibility_29a = c.eligibility_29a
        row.na_class = c.na_class
        row.confidence = c.confidence
        row.conf_class = c.conf_class
        row.bar_w = c.bar_w or c.score
    db.commit()
