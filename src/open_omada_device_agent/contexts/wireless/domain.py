"""Platform-independent wireless configuration model."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping
from ...shared.domain import DomainError, SecretValue

SSID_MAX_BYTES = 32

class InvalidSsid(DomainError):
    pass

@dataclass(frozen=True)
class Ssid:
    value: str
    def __post_init__(self) -> None:
        if len(self.value.encode("utf-8")) > SSID_MAX_BYTES:
            raise InvalidSsid("SSID must fit in 32 UTF-8 bytes")
        if "\x00" in self.value:
            raise InvalidSsid("SSID cannot contain NUL bytes")
    def __str__(self) -> str:
        return self.value

class RadioBand(str, Enum):
    TWO_G = "2g"
    FIVE_G = "5g"
    FIVE_G2 = "5g2"
    SIX_G = "6g"

@dataclass(frozen=True)
class RadioConfig:
    band: RadioBand
    radio_id: int | None = None
    enabled: bool | None = None
    channel_width: int | None = None
    channel: int | None = None
    tx_power: int | None = None
    channel_limit: bool | None = None
    wireless_mode: int | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class WirelessSecurity:
    security_mode: int | None = None
    auth_type: int | None = None
    wpa_version: int | None = None
    wpa_cipher: int | None = None
    psk_version: int | None = None
    psk_cipher: int | None = None
    psk_configured: bool = False
    psk_key: SecretValue | None = field(default=None, repr=False)
    radius_profile_id: str | None = None
    radius_auth: Mapping[str, Any] | None = None
    radius_accounting: Mapping[str, Any] | None = None
    radius_mac_auth: Mapping[str, Any] | None = None
    pmf_mode: int | None = None
    fast_roaming: bool | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class WirelessNetwork:
    band: RadioBand
    radio_id: int | None
    ssid_id: int | None
    index: int | None
    operation: int | None
    name: str
    broadcast: bool | None
    client_isolation: bool | None
    vlan: Any
    security: WirelessSecurity
    portal: Any
    raw: Mapping[str, Any] = field(default_factory=dict)

def validate_ssid_name(name: str) -> str:
    return Ssid(name).value
