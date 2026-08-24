"""Client tracking helpers fed by real platform observations."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .domain import PortalClientState, WirelessClientState
from .ecsp import normalize_mac


@dataclass(frozen=True)
class DhcpLease:
    expires_at: int
    mac: str
    ipv4: str
    hostname: str | None = None
    client_id: str | None = None


def parse_dnsmasq_leases(text: str) -> tuple[DhcpLease, ...]:
    leases: list[DhcpLease] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if len(parts) < 4:
            raise ValueError(f"invalid dnsmasq lease line {line_no}: expected at least 4 fields")
        expires, mac, ipv4, hostname = parts[:4]
        client_id = parts[4] if len(parts) > 4 and parts[4] != "*" else None
        leases.append(
            DhcpLease(
                expires_at=int(expires),
                mac=normalize_mac(mac),
                ipv4=ipv4,
                hostname=None if hostname == "*" else hostname,
                client_id=client_id,
            )
        )
    return tuple(leases)


def load_dnsmasq_leases(path: str | Path) -> tuple[DhcpLease, ...]:
    lease_path = Path(path)
    try:
        return parse_dnsmasq_leases(lease_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ()


def clients_from_dhcp_leases(leases: tuple[DhcpLease, ...]) -> tuple[WirelessClientState, ...]:
    by_mac: dict[str, DhcpLease] = {}
    for lease in leases:
        existing = by_mac.get(lease.mac)
        if existing is None or lease.expires_at >= existing.expires_at:
            by_mac[lease.mac] = lease
    return tuple(
        WirelessClientState(
            mac=lease.mac,
            ipv4=lease.ipv4,
            hostname=lease.hostname,
            portal_state=PortalClientState.UNKNOWN,
        )
        for lease in sorted(by_mac.values(), key=lambda item: item.mac)
    )


def client_stats_payload(clients: tuple[WirelessClientState, ...]) -> list[dict]:
    payload = []
    for client in clients:
        item: dict[str, object] = {"mac": client.mac}
        if client.ipv4:
            item["ip"] = client.ipv4
        if client.ipv6:
            item["ipv6List"] = list(client.ipv6)
        if client.hostname:
            item["name"] = client.hostname
        if client.ssid:
            item["ssid"] = client.ssid
        if client.radio:
            item["rid"] = _radio_id(client.radio)
        if client.rssi is not None:
            item["rssi"] = client.rssi
        if client.snr is not None:
            item["snr"] = client.snr
        if client.vlan_id is not None:
            item["vid"] = client.vlan_id
        if client.portal_state is not PortalClientState.UNKNOWN:
            item["portalStatus"] = client.portal_state.value
        item["down"] = client.rx_bytes
        item["up"] = client.tx_bytes
        if client.rx_packets is not None:
            item["rxP"] = client.rx_packets
        if client.tx_packets is not None:
            item["txP"] = client.tx_packets
        if client.rx_rate is not None:
            item["rxR"] = client.rx_rate
        if client.tx_rate is not None:
            item["txR"] = client.tx_rate
        if client.association_time is not None:
            item["aTime"] = client.association_time
        payload.append(item)
    return payload


def merge_wireless_client_states(
    *client_groups: tuple[WirelessClientState, ...],
) -> tuple[WirelessClientState, ...]:
    by_mac: dict[str, WirelessClientState] = {}
    for clients in client_groups:
        for client in clients:
            existing = by_mac.get(client.mac)
            by_mac[client.mac] = client if existing is None else _merge_client(existing, client)
    return tuple(by_mac[mac] for mac in sorted(by_mac))


def _merge_client(
    base: WirelessClientState,
    overlay: WirelessClientState,
) -> WirelessClientState:
    return WirelessClientState(
        mac=base.mac,
        ipv4=overlay.ipv4 or base.ipv4,
        ipv6=overlay.ipv6 or base.ipv6,
        hostname=overlay.hostname or base.hostname,
        ssid=overlay.ssid or base.ssid,
        radio=overlay.radio or base.radio,
        rssi=overlay.rssi if overlay.rssi is not None else base.rssi,
        snr=overlay.snr if overlay.snr is not None else base.snr,
        vlan_id=overlay.vlan_id if overlay.vlan_id is not None else base.vlan_id,
        portal_state=(
            overlay.portal_state
            if overlay.portal_state is not PortalClientState.UNKNOWN
            else base.portal_state
        ),
        rx_bytes=overlay.rx_bytes or base.rx_bytes,
        tx_bytes=overlay.tx_bytes or base.tx_bytes,
        rx_packets=(
            overlay.rx_packets if overlay.rx_packets is not None else base.rx_packets
        ),
        tx_packets=(
            overlay.tx_packets if overlay.tx_packets is not None else base.tx_packets
        ),
        rx_rate=overlay.rx_rate if overlay.rx_rate is not None else base.rx_rate,
        tx_rate=overlay.tx_rate if overlay.tx_rate is not None else base.tx_rate,
        association_time=(
            overlay.association_time
            if overlay.association_time is not None
            else base.association_time
        ),
    )


def _radio_id(radio: object) -> int | str:
    value = getattr(radio, "value", radio)
    return {
        "2g": 0,
        "5g": 1,
        "5g2": 2,
        "6g": 3,
    }.get(value, str(value))
