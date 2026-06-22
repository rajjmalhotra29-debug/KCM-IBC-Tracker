"""Web-research enrichment for IBC companies.

For each company in the feed, ask Claude (with the web-search tool) to find the
company's official website and write a short, factual profile — what it makes /
does, and any basic financials it can find. Results are cached in
data/summaries.json so each company is researched only ONCE; later runs reuse it.

Runs inside the daily/20-min GitHub Action when ANTHROPIC_API_KEY is set; it is a
no-op (profiles stay empty) without a key. Bounded by MAX_NEW per run for cost.
"""
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "summaries.json"
MAX_NEW_PER_RUN = 40

SYSTEM = """You research Indian companies that are in the insolvency / IBC process.
Using web search, find the company's OWN official website and reliable public sources
(company site, news, regulatory filings, Tofler/Zauba/MCA). Then return a SHORT,
factual profile. Do NOT invent figures — if something isn't found, say so.

Return STRICT JSON only, no prose:
{"summary":"2-3 sentence plain-English overview of the business",
 "products":"what it manufactures / the services it provides",
 "website":"official website URL, or empty string",
 "financials":"brief note of any public financials (revenue/turnover, employees, plants, year) or 'not publicly available'",
 "confidence":"high|medium|low (how reliable the sources are)"}"""


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip()).upper()


def _parse(text: str):
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b < 0:
        return None
    try:
        return json.loads(text[a:b + 1])
    except json.JSONDecodeError:
        return None


def load_cache() -> dict:
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_cache(cache: dict) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")


def _research(client, model: str, name: str, sector: str):
    msg = client.messages.create(
        model=model,
        max_tokens=900,
        system=SYSTEM,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 4}],
        messages=[{"role": "user",
                   "content": f"Company: {name}\nSector hint: {sector or '(unknown)'}\nCountry: India.\n"
                              f"Research it and return the JSON profile."}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
    data = _parse(text)
    if not data:
        return None
    data["generated"] = date.today().strftime("%d %b %Y")
    return data


def enrich(opportunities, api_key: str, model: str = "claude-sonnet-4-6") -> tuple[int, int]:
    """Attach .target.profile to each opportunity from cache; research up to
    MAX_NEW_PER_RUN uncached companies if a key is available. Returns (attached, researched)."""
    cache = load_cache()
    client = None
    if api_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
        except Exception:
            client = None

    attached = researched = 0
    for o in opportunities:
        kn = _norm(o.target.name)
        prof = cache.get(kn)
        if not prof and client and researched < MAX_NEW_PER_RUN:
            try:
                prof = _research(client, model, o.target.name, o.target.sector)
            except Exception:
                prof = None
            if prof:
                cache[kn] = prof
                researched += 1
        if prof:
            o.target.profile = prof
            attached += 1

    if researched:
        save_cache(cache)
    return attached, researched
