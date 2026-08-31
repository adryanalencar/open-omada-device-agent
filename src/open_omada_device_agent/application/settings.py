"""Immutable runtime settings consumed through application services."""
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class GenieAcsSettings:
    url: str = ""
    device_id: str = ""
    timeout_seconds: float = 10.0
    apply_timeout_seconds: float = 15.0
    verify_tls: bool = True
    ca_bundle: Path | None = None
    username: str = ""
    password: str = field(default="", repr=False)
    token: str = field(default="", repr=False)
    max_response_bytes: int = 1024 * 1024
    max_device_staleness_seconds: int = 300
    max_client_staleness_seconds: int = 120
    refresh_interval_seconds: int = 300

    def validate(self) -> None:
        parsed = urlparse(self.url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise RuntimeError("GENIEACS_URL must be an http(s) URL")
        if not self.device_id:
            raise RuntimeError("GENIEACS_DEVICE_ID is required when OPENOMADA_PLATFORM=genieacs")
        if any(ord(char) < 32 for char in self.device_id):
            raise RuntimeError("GENIEACS_DEVICE_ID must not contain control characters")
        if self.timeout_seconds <= 0:
            raise RuntimeError("GENIEACS_TIMEOUT_SECONDS must be greater than zero")
        if self.apply_timeout_seconds <= 0:
            raise RuntimeError("GENIEACS_APPLY_TIMEOUT_SECONDS must be greater than zero")
        if self.max_response_bytes <= 0:
            raise RuntimeError("GENIEACS_MAX_RESPONSE_BYTES must be greater than zero")
        if self.max_device_staleness_seconds <= 0:
            raise RuntimeError("GENIEACS_MAX_DEVICE_STALENESS_SECONDS must be greater than zero")
        if self.max_client_staleness_seconds <= 0:
            raise RuntimeError("GENIEACS_MAX_CLIENT_STALENESS_SECONDS must be greater than zero")
        if self.refresh_interval_seconds <= 0:
            raise RuntimeError("GENIEACS_REFRESH_INTERVAL_SECONDS must be greater than zero")
        if self.ca_bundle is not None and not self.ca_bundle.exists():
            raise RuntimeError(f"GENIEACS_CA_BUNDLE does not exist: {self.ca_bundle}")


@dataclass(frozen=True)
class AgentSettings:
    platform: str
    controller_host: str
    discovery_port: int
    manage_port: int
    local_discovery_port: int
    discovery_interval: float
    tcp_timeout: float
    inform_interval: float
    reconnect_delay: float
    managed_reconnect_attempts: int
    tls_verify: bool
    tls_ca_file: Path | None
    mac: str
    device_name: str
    model: str
    model_version: str
    hardware_version: str
    firmware_version: str
    customize_region: int
    device_ip: str
    public_ip_lookup_url: str
    public_ip_lookup_timeout: float
    lan_rate: float
    lan_duplex: int
    lan_port: str
    dhcp_lease_file: Path
    led_brightness_path: str
    led_on_value: str
    led_off_value: str
    led_trigger_path: str
    led_locate_trigger: str
    led_default_trigger: str
    hostapd_ubus_iface: str
    client_block_interface: str
    client_rate_limit_interface: str
    portal_interface: str
    portal_redirect_port: int
    management_vlan_interface: str
    management_vlan_device: str
    openwrt_bootstrap: bool
    openwrt_bootstrap_lan: bool
    openwrt_lan_interface: str
    openwrt_lan_bridge: str
    openwrt_lan_ipaddr: str
    openwrt_bootstrap_opennds: bool
    opennds_gateway_port: int
    opennds_gateway_name: str
    openwrt_enable_wan_management: bool
    openwrt_wan_zone: str
    lab_ack_control_plane_config: bool
    ecsp_version: str
    ecsp_ver_cap: int
    controller_id: str
    destination_controller_id: str
    site_id: str
    device_username: str
    device_password: str = field(repr=False)
    device_cipher_type: int
    state_file: Path
    capability_environment: tuple[tuple[str, str], ...]
    genieacs: GenieAcsSettings = field(default_factory=GenieAcsSettings)

    def validate(self) -> None:
        if self.platform not in {"auto", "openwrt", "generic", "genieacs"}:
            raise RuntimeError("OPENOMADA_PLATFORM/OMADA_PLATFORM must be auto, openwrt, generic or genieacs")
        if not self.controller_host:
            raise RuntimeError("OMADA_CONTROLLER_HOST is required")
        if not (1 <= self.discovery_port <= 65535 and 1 <= self.manage_port <= 65535):
            raise RuntimeError("OMADA discovery/manage ports must be between 1 and 65535")
        if self.openwrt_bootstrap and not (1 <= self.opennds_gateway_port <= 65535):
            raise RuntimeError("OMADA_OPENNDS_GATEWAY_PORT must be between 1 and 65535")
        if self.openwrt_bootstrap_lan and (
            not self.openwrt_lan_interface or not self.openwrt_lan_bridge
        ):
            raise RuntimeError(
                "OMADA_OPENWRT_LAN_INTERFACE and OMADA_OPENWRT_LAN_BRIDGE are required"
            )
        if self.openwrt_enable_wan_management and not self.openwrt_wan_zone:
            raise RuntimeError("OMADA_OPENWRT_WAN_ZONE is required")
        if self.tls_ca_file is not None and not self.tls_ca_file.exists():
            raise RuntimeError(f"OMADA_TLS_CA_FILE does not exist: {self.tls_ca_file}")
        if self.platform == "genieacs":
            self.genieacs.validate()
