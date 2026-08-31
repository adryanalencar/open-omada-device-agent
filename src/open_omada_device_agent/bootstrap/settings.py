"""Immutable settings passed from the environment boundary into the runtime."""
from pathlib import Path
import os

from .. import config
from ..application.settings import AgentSettings as RuntimeAgentSettings, GenieAcsSettings


class AgentSettings(RuntimeAgentSettings):
    @classmethod
    def from_environment(cls) -> "AgentSettings":
        """Snapshot legacy environment configuration once at composition time."""
        return cls(
            platform=config.PLATFORM,
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
            openwrt_bootstrap=config.OPENWRT_BOOTSTRAP,
            openwrt_bootstrap_lan=config.OPENWRT_BOOTSTRAP_LAN,
            openwrt_lan_interface=config.OPENWRT_LAN_INTERFACE,
            openwrt_lan_bridge=config.OPENWRT_LAN_BRIDGE,
            openwrt_lan_ipaddr=config.OPENWRT_LAN_IPADDR,
            openwrt_bootstrap_opennds=config.OPENWRT_BOOTSTRAP_OPENNDS,
            opennds_gateway_port=config.OPENNDS_GATEWAY_PORT,
            opennds_gateway_name=config.OPENNDS_GATEWAY_NAME or config.DEVICE_NAME,
            openwrt_enable_wan_management=config.OPENWRT_ENABLE_WAN_MANAGEMENT,
            openwrt_wan_zone=config.OPENWRT_WAN_ZONE,
            lab_ack_control_plane_config=config.LAB_ACK_CONTROL_PLANE_CONFIG,
            ecsp_version=config.ECSP_VERSION,
            ecsp_ver_cap=config.ECSP_VER_CAP,
            controller_id=config.CONTROLLER_ID,
            destination_controller_id=config.DEST_OMADAC_ID,
            site_id=config.SITE_ID,
            device_username=config.DEVICE_USERNAME,
            device_password=config.DEVICE_PASSWORD,
            device_cipher_type=config.DEVICE_CIPHER_TYPE,
            capability_environment=tuple(
                sorted(
                    _capability_environment_items()
                )
            ),
            genieacs=GenieAcsSettings(
                url=config.GENIEACS_URL,
                device_id=config.GENIEACS_DEVICE_ID,
                timeout_seconds=config.GENIEACS_TIMEOUT_SECONDS,
                apply_timeout_seconds=config.GENIEACS_APPLY_TIMEOUT_SECONDS,
                verify_tls=config.GENIEACS_VERIFY_TLS,
                ca_bundle=(
                    Path(config.GENIEACS_CA_BUNDLE).expanduser()
                    if config.GENIEACS_CA_BUNDLE
                    else None
                ),
                username=config.GENIEACS_USERNAME,
                password=config.GENIEACS_PASSWORD,
                token=config.GENIEACS_TOKEN,
                max_response_bytes=config.GENIEACS_MAX_RESPONSE_BYTES,
                max_device_staleness_seconds=config.GENIEACS_MAX_DEVICE_STALENESS_SECONDS,
                max_client_staleness_seconds=config.GENIEACS_MAX_CLIENT_STALENESS_SECONDS,
                refresh_interval_seconds=config.GENIEACS_REFRESH_INTERVAL_SECONDS,
            ),
        )


def _capability_environment_items() -> tuple[tuple[str, str], ...]:
    items: dict[str, str] = {}
    for name, value in os.environ.items():
        if name.startswith("OMADA_CAP_") or name in {
            "OMADA_PLATFORM",
            "OMADA_RADIO_BANDS",
            "OMADA_MAX_SSIDS",
            "OMADA_LED_BRIGHTNESS_PATH",
            "OMADA_LED_TRIGGER_PATH",
        }:
            items[name] = value
    items.setdefault("OMADA_PLATFORM", config.PLATFORM)
    return tuple(items.items())
