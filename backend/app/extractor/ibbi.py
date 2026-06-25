"""IBBI public-announcement adapter (default source).

The IBBI register (ibbi.gov.in/en/public-announcement) lists every CIRP /
liquidation / voluntary-liquidation public announcement in a single table:

  [0] Type of PA            [1] Date of Announcement   [2] Last date of Submission
  [3] Name of Corporate Debtor   [4] Name of Applicant
  [5] Name of Insolvency Professional   [6] Public Announcement (PDF)   [7] Remarks

This adapter reads those columns by header name (resilient to re-ordering),
derives the process stage, and estimates the Form G date (~75 days after a CIRP
admission). Falls back to the generic heuristics if the layout is unrecognised.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from bs4 import BeautifulSoup

from .base import USER_AGENT, ExtractedCompany, SourceAdapter
from .generic import GenericAdapter

_COL = {
    "type": re.compile(r"type of pa|type", re.I),
    "date": re.compile(r"date of announcement|date of pa", re.I),
    "submission": re.compile(r"last date|submission", re.I),
    "name": re.compile(r"corporate debtor|name of", re.I),
    "applicant": re.compile(r"applicant", re.I),
    "ip": re.compile(r"insolvency professional|resolution professional|\bip\b", re.I),
}

FORM_G_DAYS = 75  # CIRP admission -> Form G window (approx)

# crude sector inference from common tokens in Indian company names
_SECTOR_HINTS = [
    (re.compile(r"paper|pulp|kraft|board", re.I), "paper, pulp, packaging"),
    (re.compile(r"textile|cotton|yarn|denim|fabric|spinning|garment", re.I), "textile, yarn, fabric"),
    (re.compile(r"steel|ispat|iron|alloy|metal|forging|casting", re.I), "steel, iron, metal"),
    (re.compile(r"ceramic|vitrified|tile|granito|porcelain|sanitaryware", re.I), "ceramic, tile, vitrified"),
    (re.compile(r"pharma|bio|drug|life ?science|health", re.I), "pharma, bio, api"),
    (re.compile(r"chemical|polymer|resin|agro|fertiliz|pesticide", re.I), "chemical, agro"),
    (re.compile(r"agri|agro|seed|crop|food|sugar|dairy|oil ?mill", re.I), "agri, food, seed"),
    (re.compile(r"cement|concrete|infra|construct", re.I), "cement, infra"),
    (re.compile(r"power|energy|solar|electric", re.I), "power, energy"),
    (re.compile(r"auto|motor|vehicle|tyre|tire", re.I), "auto, components"),
    (re.compile(r"hotel|resort|hospitality|restaurant", re.I), "hospitality, food"),
    (re.compile(r"real ?estate|infra ?tech|developers|housing|build", re.I), "real estate"),
]


def _parse_dmy(s: str) -> datetime | None:
    s = (s or "").strip()
    m = re.match(r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})", s)
    if not m:
        return None
    try:
        return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def _infer_sector(name: str) -> str:
    for rx, label in _SECTOR_HINTS:
        if rx.search(name or ""):
            return label
    return ""


class IBBIAdapter(SourceAdapter):
    name = "ibbi"

    def extract(self, url: str, max_pages: int = 1) -> list[ExtractedCompany]:
        """Walk IBBI pages (?page=N, 20 records each) and de-duplicate.

        IBBI 301-redirects the short URL to the /en/ canonical and DROPS the query
        string, so we resolve the final URL once (from page 0) and paginate on it.
        Stops early on an empty page or one that yields nothing new.
        """
        import httpx

        out: list[ExtractedCompany] = []
        seen: set[str] = set()
        base = url
        with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30.0,
                          follow_redirects=True) as client:
            for p in range(max(1, max_pages)):
                page_url = base if p == 0 else f"{base}{'&' if '?' in base else '?'}page={p}"
                try:
                    resp = client.get(page_url)
                    resp.raise_for_status()
                except Exception:
                    break
                if p == 0:
                    # adopt the post-redirect URL so ?page= survives on later calls
                    base = str(resp.url)
                rows = self.parse(resp.text, str(resp.url))
                fresh = [r for r in rows if r.source_ref() not in seen]
                if not fresh:
                    break
                for r in fresh:
                    seen.add(r.source_ref())
                out.extend(fresh)
        return out

    def parse(self, html: str, url: str) -> list[ExtractedCompany]:
        soup = BeautifulSoup(html, "lxml")
        table = self._find_table(soup)
        if table is None:
            return GenericAdapter().parse(html, url)

        head = table.find("tr")
        headers = [c.get_text(" ", strip=True) for c in head.find_all(["th", "td"])] if head else []
        cmap = self._map_columns(headers)
        if "name" not in cmap:
            return GenericAdapter().parse(html, url)

        out: list[ExtractedCompany] = []
        for tr in table.find_all("tr")[1:]:
            cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
            if not cells:
                continue

            def col(key: str) -> str:
                i = cmap.get(key)
                return cells[i] if i is not None and i < len(cells) else ""

            name = col("name")
            if not name or len(name) < 3:
                continue

            pa_type = col("type")
            is_liq = bool(re.search(r"liquidat", pa_type, re.I))
            stage_class = "liq" if is_liq else "cirp"
            admit = col("date")
            claims_by = col("submission")

            form_g = None
            if not is_liq:
                d = _parse_dmy(admit)
                if d:
                    form_g = (d + timedelta(days=FORM_G_DAYS)).strftime("%d %b %Y")

            # Form A / public-announcement PDF. IBBI now serves it as a plain
            # <a href=...announcement/xxx.pdf download> link; older pages put the
            # URL inside an onclick="newwindow1('...pdf')". Handle both, preferring
            # the per-announcement upload path.
            pa_pdf = ""
            for a in tr.find_all("a"):
                cand = a.get("href", "") or a.get("onclick", "")
                m = re.search(r"https?://[^'\")\s]+\.pdf", cand, re.I)
                if not m:
                    continue
                url_pdf = m.group(0).strip().replace("ibbi.gov.in//", "ibbi.gov.in/")
                pa_pdf = url_pdf
                if "/uploads/announcement/" in url_pdf.lower():
                    break       # the actual Form A file — stop here

            out.append(ExtractedCompany(
                name=name,
                sector=_infer_sector(name),
                status=pa_type or ("Liquidation" if is_liq else "CIRP"),
                process_type=pa_type,
                resolution_professional=col("ip"),
                applicant=col("applicant"),
                announcement_date=admit,
                admit=admit,
                claims_by=claims_by,
                is_liq=is_liq,
                stage_label=pa_type or ("Liquidation Process" if is_liq else "Corporate Insolvency Resolution Process"),
                stage_class=stage_class,
                form_g_by=form_g,
                pa_pdf=pa_pdf,
                description=" | ".join(cells)[:1000],
                source_url=url,
            ))
        return out

    # -- helpers -------------------------------------------------------------
    @staticmethod
    def _find_table(soup: BeautifulSoup):
        tables = soup.find_all("table")
        if not tables:
            return None
        for t in tables:
            if re.search(r"corporate debtor|name of", t.get_text(" ", strip=True)[:600], re.I):
                return t
        return max(tables, key=lambda t: len(t.find_all("tr")))

    @staticmethod
    def _map_columns(headers: list[str]) -> dict[str, int]:
        cmap: dict[str, int] = {}
        for i, h in enumerate(headers):
            for key, rx in _COL.items():
                if key not in cmap and rx.search(h):
                    cmap[key] = i
        return cmap
