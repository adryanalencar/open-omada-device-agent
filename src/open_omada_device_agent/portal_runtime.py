"""Runtime wiring for captive portal enforcement."""
from __future__ import annotations

import ipaddress
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from . import config
from .domain import AccessPointConfigUpdate, PortalFreePolicy
from .openwrt import CommandRunner
from .platform_capabilities import PlatformCapabilities
from .portal_enforcement import NftablesPortalAdapter, PortalPolicy


@dataclass(frozen=True)
class PortalRuntimeResult:
    applied: bool
    changed: bool = False
    error: str = ""


class OpenWrtPortalRuntime:
    def __init__(
        self,
        runner: CommandRunner | None = None,
        *,
        interface: str | None = None,
        redirect_port: int | None = None,
    ) -> None:
        self._runner = runner
        self._interface = config.PORTAL_INTERFACE if interface is None else interface
        self._redirect_port = (
            config.PORTAL_REDIRECT_PORT if redirect_port is None else redirect_port
        )

    def reconcile(
        self,
        update: AccessPointConfigUpdate,
        capabilities: PlatformCapabilities,
    ) -> PortalRuntimeResult:
        if not _needs_portal_runtime(update):
            return PortalRuntimeResult(applied=True, changed=False)
        if not capabilities.supports_portal:
            return PortalRuntimeResult(
                applied=False,
                error="portal requested but platform capability is disabled",
            )
        if not capabilities.has_nft:
            return PortalRuntimeResult(applied=False, error="portal enforcement requires nft")
        if not self._interface:
            return PortalRuntimeResult(applied=False, error="OMADA_PORTAL_INTERFACE is required")

        policy = PortalPolicy(
            interface=self._interface,
            redirect_port=self._redirect_port,
            walled_garden_ipv4=_walled_garden_ipv4(update.portal_free_policy),
        )
        result = NftablesPortalAdapter(self._runner).apply(policy, ())
        if not result.applied:
            return PortalRuntimeResult(applied=False, error=result.error)
        return PortalRuntimeResult(applied=True, changed=True)


def _needs_portal_runtime(update: AccessPointConfigUpdate) -> bool:
    return update.portal_free_policy is not None or any(
        wlan.portal.enabled for wlan in update.wlans
    )


def _walled_garden_ipv4(policy: PortalFreePolicy | None) -> tuple[str, ...]:
    if policy is None:
        return ()
    addresses = []
    for raw_rule in _iter_rules(policy.layer2_rules):
        if address := _ipv4_from_rule(raw_rule):
            addresses.append(address)
    return tuple(dict.fromkeys(addresses))


def _iter_rules(rules: Iterable[Mapping[str, Any]]) -> Iterable[Mapping[str, Any]]:
    for rule in rules:
        yield rule
        raw_children = rule.get("children") or rule.get("entries") or ()
        if isinstance(raw_children, Iterable) and not isinstance(raw_children, (str, bytes)):
            for child in raw_children:
                if isinstance(child, Mapping):
                    yield child


def _ipv4_from_rule(rule: Mapping[str, Any]) -> str | None:
    for key in ("value", "ip", "ipAddress", "address", "dstIp", "dst"):
        raw = rule.get(key)
        if raw is None:
            continue
        try:
            address = ipaddress.ip_address(str(raw))
        except ValueError:
            continue
        if address.version == 4:
            return str(address)
    return None
