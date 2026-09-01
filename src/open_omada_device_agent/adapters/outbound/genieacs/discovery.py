"""GenieACS device discovery/probing for the selected CPE."""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Protocol

from ....application.contracts import PlatformCapabilities
from .capabilities import to_platform_capabilities
from .models import GenieAcsCapabilities, GenieAcsDeviceIdentity, GenieAcsTaskResult, Tr069DataModel
from .parameters import ParameterTree, normalize_parameters
from .profiles import Tr069DeviceProfile, UnsupportedTr069Profile, select_profile

DISCOVERY_PROJECTION = (
    "_id",
    "_deviceId",
    "_lastInform",
    "Device.DeviceInfo.",
    "Device.Ethernet.",
    "Device.IP.Interface.",
    "Device.WiFi.",
    "InternetGatewayDevice.DeviceInfo.",
    "InternetGatewayDevice.LANDevice.",
    "InternetGatewayDevice.WANDevice.",
)


class GenieAcsDeviceClient(Protocol):
    def query_device(
        self,
        device_id: str,
        *,
        projection: Sequence[str] = (),
    ) -> Mapping[str, Any] | None: ...

    def refresh_object(
        self,
        device_id: str,
        object_name: str,
        *,
        connection_request: bool = False,
    ) -> GenieAcsTaskResult: ...


class GenieAcsDiscoveryError(RuntimeError):
    """Base error for GenieACS device discovery."""


class GenieAcsDeviceNotFound(GenieAcsDiscoveryError):
    """The configured GenieACS device id was not found."""


class GenieAcsUnsupportedDevice(GenieAcsDiscoveryError):
    """The cached/probed device tree cannot be mapped to a supported profile."""


class GenieAcsProbeQueued(GenieAcsDiscoveryError):
    """A discovery refresh was queued and has not executed yet."""


@dataclass(frozen=True)
class GenieAcsDeviceSnapshot:
    device_id: str
    raw_device: Mapping[str, Any]
    parameters: ParameterTree
    profile_name: str
    data_model: Tr069DataModel
    identity: GenieAcsDeviceIdentity
    capabilities: GenieAcsCapabilities
    platform_capabilities: PlatformCapabilities
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "raw_device", MappingProxyType(dict(self.raw_device)))


class GenieAcsDeviceDiscovery:
    def __init__(
        self,
        client: GenieAcsDeviceClient,
        *,
        device_id: str,
        preferred_mac_paths: Iterable[str] = (),
        refresh_on_unsupported: bool = False,
    ) -> None:
        if not device_id:
            raise ValueError("GenieACS device discovery requires a device id")
        self._client = client
        self._device_id = device_id
        self._preferred_mac_paths = tuple(preferred_mac_paths)
        self._refresh_on_unsupported = refresh_on_unsupported

    def discover(self) -> GenieAcsDeviceSnapshot:
        raw = self._query_selected_device()
        try:
            return self._snapshot(raw)
        except GenieAcsUnsupportedDevice:
            if not self._refresh_on_unsupported:
                raise
        refresh_results = tuple(
            self._client.refresh_object(self._device_id, root, connection_request=False)
            for root in ("Device.", "InternetGatewayDevice.")
        )
        if any(result.queued for result in refresh_results):
            raise GenieAcsProbeQueued(
                "GenieACS queued device-model refresh; discovery must be retried after the CPE informs"
            )
        if not any(result.executed for result in refresh_results):
            raise GenieAcsUnsupportedDevice("GenieACS device has no supported TR-181/TR-098 tree")
        return self._snapshot(self._query_selected_device())

    def _query_selected_device(self) -> Mapping[str, Any]:
        raw = self._client.query_device(self._device_id, projection=DISCOVERY_PROJECTION)
        if raw is None:
            raise GenieAcsDeviceNotFound(f"GenieACS device not found: {self._device_id}")
        if not isinstance(raw, Mapping):
            raise GenieAcsDiscoveryError("GenieACS device query returned a non-object")
        return raw

    def _snapshot(self, raw: Mapping[str, Any]) -> GenieAcsDeviceSnapshot:
        tree = normalize_parameters(raw)
        if tree.device_id != self._device_id:
            raise GenieAcsDiscoveryError(
                f"GenieACS returned device {tree.device_id!r} for configured id {self._device_id!r}"
            )
        profile = select_profile(tree)
        if isinstance(profile, UnsupportedTr069Profile):
            raise GenieAcsUnsupportedDevice("GenieACS device has no supported TR-181/TR-098 tree")
        identity = profile.identity(tree, preferred_mac_paths=self._preferred_mac_paths)
        capabilities = profile.capabilities(tree)
        return GenieAcsDeviceSnapshot(
            device_id=self._device_id,
            raw_device=raw,
            parameters=tree,
            profile_name=profile.name,
            data_model=profile.data_model,
            identity=identity,
            capabilities=capabilities,
            platform_capabilities=to_platform_capabilities(capabilities),
            warnings=_snapshot_warnings(profile, identity, capabilities),
        )


def _snapshot_warnings(
    profile: Tr069DeviceProfile,
    identity: GenieAcsDeviceIdentity,
    capabilities: GenieAcsCapabilities,
) -> tuple[str, ...]:
    warnings: list[str] = []
    if identity.mac is None:
        warnings.append("no usable CPE MAC parameter found for Omada device identity")
    if not capabilities.has_wifi:
        warnings.append(f"{profile.name} profile matched, but no Wi-Fi objects were found")
    if capabilities.has_wifi and not capabilities.radio_bands:
        warnings.append("Wi-Fi objects were found, but no radio band parameters were available")
    return tuple(warnings)
