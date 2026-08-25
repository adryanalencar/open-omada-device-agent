"""nftables captive-portal enforcement adapter."""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass

from ....contexts.portal.domain import PortalClientState
from ....shared.domain import MacAddress
from .uci import CommandRunner, SubprocessRunner
from ....portal import PortalSession

NFT_TABLE = "openomada_portal"


@dataclass(frozen=True)
class PortalPolicy:
    interface: str
    redirect_port: int
    walled_garden_ipv4: tuple[str, ...] = ()


@dataclass(frozen=True)
class PortalEnforcementResult:
    applied: bool
    error: str = ""


class NftablesPortalAdapter:
    def __init__(self, runner: CommandRunner | None = None) -> None:
        self._runner = runner or SubprocessRunner()

    def apply(
        self,
        policy: PortalPolicy,
        sessions: tuple[PortalSession, ...],
    ) -> PortalEnforcementResult:
        try:
            rules = build_nftables_rules(policy, sessions)
        except ValueError as exc:
            return PortalEnforcementResult(applied=False, error=str(exc))

        existing = self._runner.run(["nft", "list", "table", "inet", NFT_TABLE])
        if existing.returncode == 0:
            deleted = self._runner.run(["nft", "delete", "table", "inet", NFT_TABLE])
            if deleted.returncode != 0:
                return PortalEnforcementResult(
                    applied=False,
                    error=(deleted.stderr or deleted.stdout or "nft delete table failed").strip(),
                )

        loaded = self._runner.run(["nft", "-f", "-"], input_text=rules)
        if loaded.returncode != 0:
            return PortalEnforcementResult(
                applied=False,
                error=(loaded.stderr or loaded.stdout or "nft load failed").strip(),
            )
        return PortalEnforcementResult(applied=True)


def build_nftables_rules(policy: PortalPolicy, sessions: tuple[PortalSession, ...]) -> str:
    interface = _interface_name(policy.interface)
    redirect_port = _port(policy.redirect_port)
    allowed_ips = tuple(_ipv4(value) for value in policy.walled_garden_ipv4)
    authed = tuple(
        MacAddress(session.mac).value
        for session in sessions
        if session.state is PortalClientState.AUTHENTICATED
    )
    blocked = tuple(
        MacAddress(session.mac).value
        for session in sessions
        if session.state is PortalClientState.BLOCKED
    )

    lines = [
        f"table inet {NFT_TABLE} {{",
        *_set_lines("authed_macs", "ether_addr", authed),
        *_set_lines("blocked_macs", "ether_addr", blocked),
        *_set_lines("walled_garden_v4", "ipv4_addr", allowed_ips),
        "  chain forward {",
        "    type filter hook forward priority filter; policy accept;",
        f"    iifname \"{interface}\" ether saddr @blocked_macs drop",
        f"    iifname \"{interface}\" ether saddr @authed_macs accept",
        f"    iifname \"{interface}\" udp dport {{ 53, 67, 68 }} accept",
        f"    iifname \"{interface}\" ip daddr @walled_garden_v4 accept",
        f"    iifname \"{interface}\" tcp dport 443 drop",
        f"    iifname \"{interface}\" drop",
        "  }",
        "  chain prerouting {",
        "    type nat hook prerouting priority dstnat; policy accept;",
        f"    iifname \"{interface}\" ether saddr @authed_macs accept",
        f"    iifname \"{interface}\" ip daddr @walled_garden_v4 accept",
        f"    iifname \"{interface}\" tcp dport 80 redirect to :{redirect_port}",
        "  }",
        "}",
    ]
    return "\n".join(lines) + "\n"


def _set_lines(name: str, nft_type: str, values: tuple[str, ...]) -> tuple[str, ...]:
    lines = [
        f"  set {name} {{",
        f"    type {nft_type}",
    ]
    if values:
        lines.append(f"    elements = {{ {', '.join(values)} }}")
    lines.append("  }")
    return tuple(lines)


def _interface_name(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,32}", value):
        raise ValueError(f"invalid portal interface name: {value!r}")
    return value


def _port(value: int) -> int:
    port = int(value)
    if not 1 <= port <= 65535:
        raise ValueError(f"invalid portal redirect port: {value}")
    return port


def _ipv4(value: str) -> str:
    address = ipaddress.ip_address(value)
    if address.version != 4:
        raise ValueError(f"portal walled garden address must be IPv4: {value}")
    return str(address)
