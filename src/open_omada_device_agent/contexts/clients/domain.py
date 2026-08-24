"""Unified client state assembled from independent observation sources."""
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Mapping
from ...shared.domain import MacAddress
from ..portal.domain import PortalClientState
from ..wireless.domain import RadioBand

class ClientOperationCode(IntEnum):
    BLOCK = 0
    UNBLOCK = 1
    RECONNECT = 2
    PORTAL_UNAUTH = 3
    LOCK_TO_AP_BLOCK = 6
    LOCK_TO_AP_UNBLOCK = 7
    LOCK_ALLOW = 10

@dataclass(frozen=True)
class ClientAuthConfig:
    client_mac: str
    unauthenticated: bool | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class ClientControlOperation:
    client_mac: str
    operation: int | None = None
    ssid: str | None = None
    radio_id: int | None = None
    vid: int | None = None
    port: int | None = None
    wireless: bool | None = None
    source_key: str = "clientOperation"
    raw: Mapping[str, Any] = field(default_factory=dict)
    @property
    def operation_code(self) -> ClientOperationCode | None:
        try:
            return None if self.operation is None else ClientOperationCode(self.operation)
        except ValueError:
            return None

@dataclass(frozen=True)
class ClientRateLimit:
    mac: str
    down: int | None = None
    up: int | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class ClientRateConfig:
    action: int | None = None
    limits: tuple[ClientRateLimit, ...] = ()
    raw: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class WirelessClientState:
    mac: str
    ipv4: str | None = None
    ipv6: tuple[str, ...] = ()
    hostname: str | None = None
    ssid: str | None = None
    radio: RadioBand | None = None
    rssi: int | None = None
    snr: int | None = None
    vlan_id: int | None = None
    portal_state: PortalClientState = PortalClientState.UNKNOWN
    rx_bytes: int = 0
    tx_bytes: int = 0
    rx_packets: int | None = None
    tx_packets: int | None = None
    rx_rate: int | None = None
    tx_rate: int | None = None
    association_time: int | None = None
    def __post_init__(self) -> None:
        object.__setattr__(self, "mac", MacAddress(self.mac).value)

@dataclass(frozen=True)
class LedConfig:
    enabled: bool | None = None
    locate: bool | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class WifiControlLedConfig:
    enabled: bool | None = None
    is_pressed: bool | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)
