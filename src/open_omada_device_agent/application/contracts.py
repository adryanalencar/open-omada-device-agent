"""Application-level contracts shared by orchestration ports."""
from dataclasses import dataclass

from ..contexts.wireless.domain import RadioBand

@dataclass(frozen=True)
class PlatformCapabilities:
    platform: str
    has_uci: bool = False
    has_ubus: bool = False
    has_nft: bool = False
    has_hostapd: bool = False
    has_dnsmasq: bool = False
    has_opennds: bool = False
    radio_bands: tuple[RadioBand, ...] = ()
    max_ssids: int = 0
    supports_wlan_config: bool = False
    supports_wpa2_psk: bool = False
    supports_wpa3_psk: bool = False
    supports_wpa_enterprise: bool = False
    supports_radius: bool = False
    supports_ssid_vlan: bool = False
    supports_dynamic_vlan: bool = False
    supports_management_vlan: bool = False
    supports_portal: bool = False
    supports_dhcp_tracking: bool = False
    supports_option82: bool = False
    supports_led_control: bool = False
    supports_client_operations: bool = False
    supports_client_rate_limits: bool = False
