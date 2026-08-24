"""Compatibility façade for domain types now owned by bounded contexts.

New code must import a context's public API. This façade remains for external
callers while the package migrates incrementally.
"""
from .contexts.clients.domain import (  # noqa: F401
    ClientAuthConfig, ClientControlOperation, ClientOperationCode,
    ClientRateConfig, ClientRateLimit, LedConfig, WifiControlLedConfig,
    WirelessClientState,
)
from .contexts.networking.domain import (  # noqa: F401
    DhcpOption82, ManagementVlan, VlanAssignment, validate_vlan_id,
)
from .contexts.portal.domain import (  # noqa: F401
    CaptivePortalBinding, PortalClientState, PortalFreePolicy,
)
from .contexts.wireless.domain import (  # noqa: F401
    RadioBand, RadioConfig, WirelessNetwork, WirelessSecurity, validate_ssid_name,
)
from .shared.domain import SecretValue  # noqa: F401
from dataclasses import dataclass, field
from typing import Any, Mapping

@dataclass(frozen=True)
class AccessPointConfigUpdate:
    """Transitional aggregate command spanning configuration contexts."""
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
    unhandled_keys: tuple[str, ...] = ()
    raw_body: Mapping[str, Any] = field(default_factory=dict)

__all__ = [name for name in globals() if not name.startswith("_")]
