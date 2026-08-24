"""Immutable settings passed from the environment boundary into the runtime."""
from pathlib import Path

from .. import config
from ..application.settings import AgentSettings as RuntimeAgentSettings


class AgentSettings(RuntimeAgentSettings):
    @classmethod
    def from_environment(cls) -> "AgentSettings":
        """Snapshot legacy environment configuration once at composition time."""
        return cls(
            controller_host=config.CONTROLLER_HOST,
            discovery_port=config.DISCOVERY_PORT,
            manage_port=config.MANAGE_PORT,
            local_discovery_port=config.LOCAL_DISCOVERY_PORT,
            discovery_interval=config.DISCOVERY_INTERVAL,
            tcp_timeout=config.TCP_TIMEOUT,
            inform_interval=config.INFORM_INTERVAL,
            reconnect_delay=config.RECONNECT_DELAY,
            managed_reconnect_attempts=config.MANAGED_RECONNECT_ATTEMPTS,
            tls_verify=config.TLS_VERIFY,
            state_file=Path(config.STATE_FILE).expanduser(),
            tls_ca_file=Path(config.TLS_CA_FILE).expanduser() if config.TLS_CA_FILE else None,
            mac=config.MAC,
            device_name=config.DEVICE_NAME,
            model=config.MODEL,
            model_version=config.MODEL_VERSION,
            hardware_version=config.HARDWARE_VERSION,
            firmware_version=config.FIRMWARE_VERSION,
            customize_region=config.CUSTOMIZE_REGION,
            device_ip=config.DEVICE_IP,
            public_ip_lookup_url=config.PUBLIC_IP_LOOKUP_URL,
            public_ip_lookup_timeout=config.PUBLIC_IP_LOOKUP_TIMEOUT,
            lan_rate=config.LAN_RATE,
            lan_duplex=config.LAN_DUPLEX,
            lan_port=config.LAN_PORT,
            dhcp_lease_file=Path(config.DHCP_LEASE_FILE),
            led_brightness_path=config.LED_BRIGHTNESS_PATH,
            led_on_value=config.LED_ON_VALUE,
            led_off_value=config.LED_OFF_VALUE,
            led_trigger_path=config.LED_TRIGGER_PATH,
            led_locate_trigger=config.LED_LOCATE_TRIGGER,
            led_default_trigger=config.LED_DEFAULT_TRIGGER,
            hostapd_ubus_iface=config.HOSTAPD_UBUS_IFACE,
            client_block_interface=config.CLIENT_BLOCK_INTERFACE,
            client_rate_limit_interface=config.CLIENT_RATE_LIMIT_INTERFACE,
            portal_interface=config.PORTAL_INTERFACE,
            portal_redirect_port=config.PORTAL_REDIRECT_PORT,
            management_vlan_interface=config.MANAGEMENT_VLAN_INTERFACE,
            management_vlan_device=config.MANAGEMENT_VLAN_DEVICE,
            ecsp_version=config.ECSP_VERSION,
            ecsp_ver_cap=config.ECSP_VER_CAP,
            controller_id=config.CONTROLLER_ID,
            destination_controller_id=config.DEST_OMADAC_ID,
            site_id=config.SITE_ID,
            device_username=config.DEVICE_USERNAME,
            device_password=config.DEVICE_PASSWORD,
            device_cipher_type=config.DEVICE_CIPHER_TYPE,
        )
