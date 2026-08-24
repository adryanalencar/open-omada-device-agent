"""Immutable runtime settings consumed through application services."""
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class AgentSettings:
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

    def validate(self) -> None:
        if not self.controller_host:
            raise RuntimeError("OMADA_CONTROLLER_HOST is required")
        if not (1 <= self.discovery_port <= 65535 and 1 <= self.manage_port <= 65535):
            raise RuntimeError("OMADA discovery/manage ports must be between 1 and 65535")
        if self.tls_ca_file is not None and not self.tls_ca_file.exists():
            raise RuntimeError(f"OMADA_TLS_CA_FILE does not exist: {self.tls_ca_file}")
