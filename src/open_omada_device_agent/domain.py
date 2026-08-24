"""Compatibility façade for domain types now owned by bounded contexts.

New code must import a context's public API. This façade remains for external
callers while the package migrates incrementally.
"""
from .contexts.clients.domain import (  # noqa: F401
    ClientAuthConfig, ClientControlOperation, ClientOperationCode,
    ClientRateConfig, ClientRateLimit,
    WirelessClientState,
)
from .contexts.device.domain import LedConfig, WifiControlLedConfig  # noqa: F401
from .contexts.networking.domain import (  # noqa: F401
    DhcpOption82, ManagementVlan, VlanAssignment, validate_vlan_id,
)
from .contexts.portal.domain import (  # noqa: F401
    CaptivePortalBinding, PortalClientState, PortalFreePolicy,
)
from .contexts.wireless.domain import (  # noqa: F401
    CaptivePortalIntent, RadioBand, RadioConfig, WirelessDhcpOption82Intent,
    WirelessNetwork, WirelessSecurity, WirelessVlanIntent, validate_ssid_name,
)
from .shared.domain import SecretValue  # noqa: F401
from .application.commands import ApplyDeviceConfigurationCommand

AccessPointConfigUpdate = ApplyDeviceConfigurationCommand

__all__ = [name for name in globals() if not name.startswith("_")]
