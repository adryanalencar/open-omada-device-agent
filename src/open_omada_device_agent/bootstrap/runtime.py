"""The sole default wiring point for application ports and concrete adapters."""
from dataclasses import dataclass
from functools import lru_cache, partial
import logging

from ..application.configuration import ApplyDeviceConfiguration
from ..application.contracts import PlatformCapabilities
from ..adapters.outbound.openwrt.bootstrap import OpenWrtBootstrapConfig, OpenWrtStartupBootstrap
from ..adapters.outbound.openwrt.device_commands import OpenWrtClientControlAdapter, SysfsLedAdapter
from ..adapters.outbound.openwrt.uci import OpenWrtUciAdapter
from ..adapters.outbound.openwrt.capabilities import detect_platform_capabilities
from ..adapters.outbound.openwrt.portal_runtime import OpenWrtPortalRuntime
from ..adapters.outbound.openwrt.client_observations import client_stats_payload, clients_from_dhcp_leases, load_dnsmasq_leases, merge_wireless_client_states
from ..network_tools import get_public_ip
from ..adapters.outbound.openwrt.device_profile import GenericOpenWrtAccessPointProfile
from .settings import AgentSettings
from ..projections.inform import InformAssembler, LanObservation
from ..contexts.lifecycle.infrastructure.session_state import JsonSessionStateRepository
from ..adapters.outbound.openwrt.telemetry import collect_openwrt_wireless_clients, collect_openwrt_wireless_inform
from ..adapters.outbound.openwrt.opennds import collect_opennds_clients


log = logging.getLogger("open_omada.bootstrap")


@dataclass(frozen=True)
class AgentRuntime:
    configuration: ApplyDeviceConfiguration
    inform: InformAssembler
    state_repository: JsonSessionStateRepository
    settings: AgentSettings
    device_profile: GenericOpenWrtAccessPointProfile
    capabilities: PlatformCapabilities


@lru_cache(maxsize=1)
def build_runtime(settings: AgentSettings) -> AgentRuntime:
    """Build production dependencies; tests may construct the use cases directly."""
    capabilities = detect_platform_capabilities(env=dict(settings.capability_environment))
    bootstrap_result = OpenWrtStartupBootstrap(
        config=OpenWrtBootstrapConfig(
            enabled=settings.openwrt_bootstrap,
            ensure_lan=settings.openwrt_bootstrap_lan,
            lan_interface=settings.openwrt_lan_interface,
            lan_bridge=settings.openwrt_lan_bridge,
            lan_ipaddr=settings.openwrt_lan_ipaddr,
            ensure_opennds=settings.openwrt_bootstrap_opennds,
            opennds_gateway_port=settings.opennds_gateway_port,
            opennds_gateway_name=settings.opennds_gateway_name,
            enable_wan_management=settings.openwrt_enable_wan_management,
            wan_zone=settings.openwrt_wan_zone,
        )
    ).apply(capabilities)
    if bootstrap_result.warnings:
        log.warning(
            "OpenWrt bootstrap completed with warning(s): %s",
            "; ".join(bootstrap_result.warnings),
        )
    profile = GenericOpenWrtAccessPointProfile(
        settings,
        ip_address=partial(
            get_public_ip,
            settings.device_ip,
            settings.public_ip_lookup_url,
            settings.public_ip_lookup_timeout,
        ),
        capabilities=capabilities,
    )
    return AgentRuntime(
        configuration=ApplyDeviceConfiguration(
            capability_detector=lambda: capabilities,
            platform_ports=(
                OpenWrtUciAdapter(
                    management_vlan_interface=settings.management_vlan_interface,
                    management_vlan_device=settings.management_vlan_device,
                ),
                OpenWrtPortalRuntime(
                    interface=settings.portal_interface,
                    redirect_port=settings.portal_redirect_port,
                ),
            ),
            command_ports=(
                SysfsLedAdapter(
                    brightness_path=settings.led_brightness_path,
                    trigger_path=settings.led_trigger_path,
                    on_value=settings.led_on_value,
                    off_value=settings.led_off_value,
                    locate_trigger=settings.led_locate_trigger,
                    default_trigger=settings.led_default_trigger,
                ),
                OpenWrtClientControlAdapter(
                    hostapd_iface=settings.hostapd_ubus_iface,
                    block_interface=settings.client_block_interface,
                    rate_limit_interface=settings.client_rate_limit_interface,
                ),
            ),
            allow_ack_only_config=settings.lab_ack_control_plane_config,
        ),
        inform=InformAssembler(
            device_info=profile.device_info,
            lan=LanObservation(settings.lan_rate, settings.lan_duplex, settings.lan_port),
            clients=lambda: merge_wireless_client_states(
                clients_from_dhcp_leases(load_dnsmasq_leases(settings.dhcp_lease_file)),
                collect_openwrt_wireless_clients(capabilities=capabilities),
                collect_opennds_clients(capabilities=capabilities),
            ),
            client_projection=client_stats_payload,
            wireless_projection=lambda: collect_openwrt_wireless_inform(
                capabilities=capabilities
            ),
        ),
        state_repository=JsonSessionStateRepository(
            settings.state_file,
            device_mac=settings.mac,
            controller_host=settings.controller_host,
        ),
        settings=settings,
        device_profile=profile,
        capabilities=capabilities,
    )
