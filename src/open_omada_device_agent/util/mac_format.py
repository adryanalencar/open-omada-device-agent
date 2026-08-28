from __future__ import annotations

from ..shared.domain import MacAddress


def to_omada(mac: str) -> str:
    """Convert a MAC address to Omada's dash-separated upper-case format."""
    return MacAddress(mac).omada
