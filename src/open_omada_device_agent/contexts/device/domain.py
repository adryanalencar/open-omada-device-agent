"""Static device identity and profile contracts."""
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol
from ...shared.domain import MacAddress

@dataclass(frozen=True)
class DeviceIdentity:
    mac: MacAddress
    name: str
    model: str
    model_version: str
    hardware_version: str
    firmware_version: str

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

class DeviceProfile(Protocol):
    def identity(self) -> DeviceIdentity: ...
    def device_info(self) -> Mapping[str, Any]: ...
    def device_misc(self) -> Mapping[str, Any]: ...
    def components_v2(self) -> Mapping[str, str]: ...
