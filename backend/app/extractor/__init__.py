"""Pluggable IBC source extractors.

Add the exact daily-listing site later by writing one adapter class and
registering it in ADAPTERS — nothing else changes.
"""
from .base import ExtractedCompany, SourceAdapter
from .generic import GenericAdapter
from .ibbi import IBBIAdapter

ADAPTERS: dict[str, type[SourceAdapter]] = {
    "ibbi": IBBIAdapter,
    "generic": GenericAdapter,
}


def get_adapter(name: str) -> SourceAdapter:
    cls = ADAPTERS.get(name, GenericAdapter)
    return cls()


__all__ = ["ExtractedCompany", "SourceAdapter", "get_adapter", "ADAPTERS"]
