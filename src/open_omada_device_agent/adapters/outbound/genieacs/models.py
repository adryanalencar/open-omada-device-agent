"""Typed GenieACS NBI results shared by adapter modules."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from ....contexts.wireless.domain import RadioBand


class Tr069DataModel(str, Enum):
    TR181 = "tr181"
    TR098 = "tr098"
    DUAL = "dual"
    UNKNOWN = "unknown"


class GenieAcsTaskState(str, Enum):
    EXECUTED = "executed"
    QUEUED = "queued"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class GenieAcsTaskResult:
    state: GenieAcsTaskState
    status_code: int
    payload: Any = None
    task_id: str | None = None
    faults: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)

    @property
    def executed(self) -> bool:
        return self.state is GenieAcsTaskState.EXECUTED

    @property
    def queued(self) -> bool:
        return self.state is GenieAcsTaskState.QUEUED

    @property
    def failed(self) -> bool:
        return self.state is GenieAcsTaskState.FAILED


@dataclass(frozen=True)
class GenieAcsDeviceIdentity:
    genieacs_id: str
    manufacturer: str | None = None
    oui: str | None = None
    product_class: str | None = None
    serial_number: str | None = None
    software_version: str | None = None
    hardware_version: str | None = None
    mac: str | None = None
    mac_source: str | None = None


@dataclass(frozen=True)
class MacCandidate:
    path: str
    role: str
    priority: int


@dataclass(frozen=True)
class MacSelection:
    mac: str
    path: str
    role: str


@dataclass(frozen=True)
class Tr069ObjectRef:
    path: str
    instance: str


@dataclass(frozen=True)
class GenieAcsCapabilities:
    profile: str
    data_model: Tr069DataModel
    has_device_info: bool = False
    has_wifi: bool = False
    radio_count: int = 0
    ssid_count: int = 0
    access_point_count: int = 0
    client_table_count: int = 0
    radio_bands: tuple[RadioBand, ...] = ()
    supports_radio_read: bool = False
    supports_radio_enable: bool = False
    supports_channel_write: bool = False
    supports_ssid_read: bool = False
    supports_ssid_write: bool = False
    supports_wpa2_psk: bool = False
    supports_clients: bool = False
    supports_client_signal: bool = False
    supports_client_traffic: bool = False
    supports_vlan: bool = False
    supports_portal: bool = False
    supports_client_control: bool = False
