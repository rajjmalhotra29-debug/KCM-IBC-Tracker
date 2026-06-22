"""Extractor contract shared by every source adapter."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import httpx

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) IBC-Matchmaker/0.1 "
    "(+research; contact admin)"
)


@dataclass
class ExtractedCompany:
    """One distressed company pulled off a source page."""
    name: str
    sector: str = ""
    products: str = ""
    raw_materials: str = ""
    customers: str = ""
    description: str = ""
    status: str = ""
    process_type: str = ""
    resolution_professional: str = ""
    location: str = ""
    announcement_date: str = ""
    source_url: str = ""
    # Jarvis process / Form-G fields
    is_liq: bool = False
    stage_label: str = ""
    stage_class: str = "cirp"
    applicant: str = ""
    admit: str = ""
    claims_by: str = ""
    form_g_by: str | None = None
    pa_pdf: str = ""          # Form A / public-announcement PDF (direct URL)
    extra: dict = field(default_factory=dict)

    def source_ref(self) -> str:
        """Stable de-dup key for this record."""
        basis = f"{self.name}|{self.announcement_date}|{self.source_url}".lower().strip()
        return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:24]


class SourceAdapter:
    """Base adapter. Subclass and implement parse()."""
    name = "base"

    def fetch(self, url: str, timeout: float = 30.0) -> str:
        with httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
            follow_redirects=True,
        ) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.text

    def parse(self, html: str, url: str) -> list[ExtractedCompany]:  # pragma: no cover
        raise NotImplementedError

    def extract(self, url: str, max_pages: int = 1) -> list[ExtractedCompany]:
        # Single-page by default; paginating adapters (e.g. IBBI) override this.
        return self.parse(self.fetch(url), url)
