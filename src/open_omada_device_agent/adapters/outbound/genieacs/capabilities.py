"""Capability mapping for GenieACS-backed TR-069 profiles."""
from __future__ import annotations

from ....application.contracts import PlatformCapabilities
from ....contexts.wireless.domain import RadioBand
from .models import GenieAcsCapabilities


def to_platform_capabilities(capabilities: GenieAcsCapabilities) -> PlatformCapabilities:
    """Map profile-local capabilities onto existing application port capabilities.

    This is intentionally conservative and does not imply runtime wiring. It is
    provided so later phases can inject GenieACS behind the same application
    ports that OpenWrt already uses.
    """
    return PlatformCapabilities(
        platform="genieacs",
        radio_bands=_unique_bands(capabilities.radio_bands),
        max_ssids=capabilities.ssid_count,
        supports_wlan_config=(
            capabilities.supports_radio_enable
            or capabilities.supports_channel_write
            or capabilities.supports_ssid_write
            or capabilities.supports_wpa2_psk
        ),
        supports_wpa2_psk=capabilities.supports_wpa2_psk,
        supports_wpa3_psk=False,
        supports_wpa_enterprise=False,
        supports_radius=False,
        supports_ssid_vlan=capabilities.supports_vlan,
        supports_dynamic_vlan=False,
        supports_management_vlan=False,
        supports_portal=False,
        supports_dhcp_tracking=capabilities.supports_clients,
        supports_option82=False,
        supports_led_control=False,
        supports_client_operations=False,
        supports_client_rate_limits=False,
    )


def _unique_bands(bands: tuple[RadioBand, ...]) -> tuple[RadioBand, ...]:
    return tuple(dict.fromkeys(bands))
