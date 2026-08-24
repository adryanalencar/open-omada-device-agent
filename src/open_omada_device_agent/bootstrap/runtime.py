"""The sole default wiring point for application ports and concrete adapters."""
from dataclasses import dataclass
from functools import lru_cache

from ..application.configuration import ApplyDeviceConfiguration
from ..adapters.outbound.openwrt.device_commands import OpenWrtClientControlAdapter, SysfsLedAdapter
from ..adapters.outbound.openwrt.uci import OpenWrtUciAdapter
from ..adapters.outbound.openwrt.capabilities import detect_platform_capabilities
from ..adapters.outbound.openwrt.portal_runtime import OpenWrtPortalRuntime
from .. import config
from ..adapters.outbound.openwrt.client_observations import client_stats_payload, clients_from_dhcp_leases, load_dnsmasq_leases, merge_wireless_client_states
from ..identity import device_info
from ..projections.inform import InformAssembler, LanObservation
from ..contexts.lifecycle.infrastructure.session_state import JsonSessionStateRepository
from ..adapters.outbound.openwrt.telemetry import collect_openwrt_wireless_clients, collect_openwrt_wireless_inform


@dataclass(frozen=True)
class AgentRuntime:
    configuration: ApplyDeviceConfiguration
    inform: InformAssembler
    state_repository: JsonSessionStateRepository


@lru_cache(maxsize=1)
def build_runtime() -> AgentRuntime:
    """Build production dependencies; tests may construct the use cases directly."""
    return AgentRuntime(
        configuration=ApplyDeviceConfiguration(
            capability_detector=detect_platform_capabilities,
            platform_ports=(OpenWrtUciAdapter(), OpenWrtPortalRuntime()),
            command_ports=(SysfsLedAdapter(), OpenWrtClientControlAdapter()),
        ),
        inform=InformAssembler(
            device_info=device_info,
            lan=LanObservation(config.LAN_RATE, config.LAN_DUPLEX, config.LAN_PORT),
            clients=lambda: merge_wireless_client_states(
                clients_from_dhcp_leases(load_dnsmasq_leases(config.DHCP_LEASE_FILE)),
                collect_openwrt_wireless_clients(),
            ),
            client_projection=client_stats_payload,
            wireless_projection=collect_openwrt_wireless_inform,
        ),
        state_repository=JsonSessionStateRepository(),
    )
