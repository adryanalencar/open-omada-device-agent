"""Typed aggregate commands crossing configuration bounded contexts."""
from dataclasses import dataclass, field
from typing import Any, Mapping

from ..contexts.clients.domain import ClientAuthConfig, ClientControlOperation, ClientRateConfig
from ..contexts.device.domain import LedConfig, WifiControlLedConfig
from ..contexts.networking.domain import ManagementVlan
from ..contexts.portal.domain import PortalFreePolicy
from ..contexts.wireless.domain import RadioConfig, WirelessNetwork

@dataclass(frozen=True)
class ApplyDeviceConfigurationCommand:
    sequence_id: int | None
    config_version: int | None
    config_version_inc: int | None
    radios: tuple[RadioConfig, ...] = ()
    wlans: tuple[WirelessNetwork, ...] = ()
    management_vlan: ManagementVlan | None = None
    portal_free_policy: PortalFreePolicy | None = None
    led: LedConfig | None = None
    wifi_control_led: WifiControlLedConfig | None = None
    client_configs: tuple[ClientAuthConfig, ...] = ()
    client_operations: tuple[ClientControlOperation, ...] = ()
    client_rate_config: ClientRateConfig | None = None
    passive_keys: tuple[str, ...] = ()
    ack_only_keys: tuple[str, ...] = ()
    unhandled_keys: tuple[str, ...] = ()
    raw_body: Mapping[str, Any] = field(default_factory=dict)
