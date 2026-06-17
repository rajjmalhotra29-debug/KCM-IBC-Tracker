"""Generic fallback adapter.

Heuristically pulls company-like rows from any HTML page (tables first, then
list items / cards). Deliberately conservative: better to return a few clean
rows than a lot of noise. When an Anthropic key is configured, it can hand the
page text to the AI for a far cleaner structured extraction.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .base import ExtractedCompany, SourceAdapter

# Words that hint a column / cell holds a company name.
_NAME_HINTS = re.compile(r"(corporate debtor|company|name of|entity|debtor)", re.I)
_STATUS_HINTS = re.compile(r"(cirp|liquidation|insolvency|resolution|auction|voluntary)", re.I)
_DATE_RE = re.compile(r"\b(\d{1,2}[-/ ][A-Za-z0-9]{2,9}[-/ ]\d{2,4})\b")


class GenericAdapter(SourceAdapter):
    name = "generic"

    def parse(self, html: str, url: str) -> list[ExtractedCompany]:
        soup = BeautifulSoup(html, "lxml")
        rows = self._from_tables(soup, url)
        if rows:
            return rows
        return self._from_lists(soup, url)

    # -- tables --------------------------------------------------------------
    def _from_tables(self, soup: BeautifulSoup, url: str) -> list[ExtractedCompany]:
        out: list[ExtractedCompany] = []
        for table in soup.find_all("table"):
            headers = [th.get_text(" ", strip=True) for th in table.find_all("th")]
            name_idx = self._guess_name_col(headers)
            for tr in table.find_all("tr"):
                cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
                if not cells:
                    continue
                name = self._pick_name(cells, name_idx)
                if not name or len(name) < 3:
                    continue
                joined = " | ".join(cells)
                out.append(
                    ExtractedCompany(
                        name=name,
                        status=self._first_match(_STATUS_HINTS, joined),
                        announcement_date=self._first_date(joined),
                        description=joined[:1000],
                        source_url=url,
                    )
                )
        return out

    def _from_lists(self, soup: BeautifulSoup, url: str) -> list[ExtractedCompany]:
        out: list[ExtractedCompany] = []
        for li in soup.find_all(["li", "article"]):
            text = li.get_text(" ", strip=True)
            if len(text) < 12 or not _STATUS_HINTS.search(text):
                continue
            name = text.split(" - ")[0].split(",")[0][:200]
            out.append(
                ExtractedCompany(
                    name=name,
                    status=self._first_match(_STATUS_HINTS, text),
                    announcement_date=self._first_date(text),
                    description=text[:1000],
                    source_url=url,
                )
            )
        return out[:200]

    # -- helpers -------------------------------------------------------------
    @staticmethod
    def _guess_name_col(headers: list[str]) -> int | None:
        for i, h in enumerate(headers):
            if _NAME_HINTS.search(h):
                return i
        return None

    @staticmethod
    def _pick_name(cells: list[str], idx: int | None) -> str:
        if idx is not None and idx < len(cells):
            return cells[idx]
        # fall back to the longest alphabetic-ish cell
        cand = [c for c in cells if re.search(r"[A-Za-z]{3,}", c)]
        return max(cand, key=len) if cand else ""

    @staticmethod
    def _first_match(rx: re.Pattern, text: str) -> str:
        m = rx.search(text)
        return m.group(0) if m else ""

    @staticmethod
    def _first_date(text: str) -> str:
        m = _DATE_RE.search(text)
        return m.group(1) if m else ""
