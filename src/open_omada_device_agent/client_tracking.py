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
        if client.hostname:
            item["deviceName"] = client.hostname
        if client.ssid:
            item["ssid"] = client.ssid
        if client.radio:
            item["radioId"] = client.radio.value
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
        payload.append(item)
    return payload
