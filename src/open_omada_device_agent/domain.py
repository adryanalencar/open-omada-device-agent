"""Omada AP domain models independent from ECSP framing and platform adapters."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

VLAN_MIN = 1
VLAN_MAX = 4094
SSID_MAX_BYTES = 32


class RadioBand(str, Enum):
    TWO_G = "2g"
    FIVE_G = "5g"
    FIVE_G2 = "5g2"
    SIX_G = "6g"


class PortalClientState(str, Enum):
    UNKNOWN = "unknown"
    UNAUTHENTICATED = "unauthenticated"
    AUTHENTICATING = "authenticating"
    AUTHENTICATED = "authenticated"
    EXPIRED = "expired"
    BLOCKED = "blocked"


@dataclass(frozen=True, repr=False)
class SecretValue:
    value: str

    def reveal(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return "SecretValue(***)"

    __str__ = __repr__


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
class DhcpOption82:
    enabled: bool = False
    format: int | None = None
    delimiter: str | None = None
    circuit_id: tuple[int, ...] = ()
    remote_id: tuple[int, ...] = ()
    site_name: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VlanAssignment:
    vlan_id: int | None = None
    vlan_pool_ids: tuple[str, ...] = ()
    dynamic_vlan_mode: int | None = None
    dhcp_option82: DhcpOption82 | None = None


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
class CaptivePortalBinding:
    enabled: bool = False
    https_redirect: bool | None = None
    hotspot_v2: Mapping[str, Any] | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)


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
    vlan: VlanAssignment
    security: WirelessSecurity
    portal: CaptivePortalBinding
    raw: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ManagementVlan:
    enabled: bool
    vlan_id: int | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PortalFreePolicy:
    layer2_rules: tuple[Mapping[str, Any], ...] = ()
    url_rules: tuple[Mapping[str, Any], ...] = ()
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


@dataclass(frozen=True)
class AccessPointConfigUpdate:
    sequence_id: int | None
    config_version: int | None
    config_version_inc: int | None
    radios: tuple[RadioConfig, ...] = ()
    wlans: tuple[WirelessNetwork, ...] = ()
    management_vlan: ManagementVlan | None = None
    portal_free_policy: PortalFreePolicy | None = None
    led: LedConfig | None = None
    wifi_control_led: WifiControlLedConfig | None = None
    unhandled_keys: tuple[str, ...] = ()
    raw_body: Mapping[str, Any] = field(default_factory=dict)


def validate_vlan_id(vlan_id: int) -> int:
    if not VLAN_MIN <= int(vlan_id) <= VLAN_MAX:
        raise ValueError(f"VLAN ID must be between {VLAN_MIN} and {VLAN_MAX}: {vlan_id}")
    return int(vlan_id)


def validate_ssid_name(name: str) -> str:
    encoded = name.encode("utf-8")
    if len(encoded) > SSID_MAX_BYTES:
        raise ValueError("SSID must fit in 32 UTF-8 bytes")
    if "\x00" in name:
        raise ValueError("SSID cannot contain NUL bytes")
    return name
