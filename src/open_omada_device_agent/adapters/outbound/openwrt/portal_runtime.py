"""Runtime wiring for captive portal enforcement."""
from __future__ import annotations

import ipaddress
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .... import config
from ....application.commands import ApplyDeviceConfigurationCommand
from ....contexts.portal.domain import PortalFreePolicy
from .uci import CommandRunner
from ....application.contracts import PlatformCapabilities
from .opennds import OpenNdsPortalAdapter, opennds_portal_policy_from_omada_config
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
        update: ApplyDeviceConfigurationCommand,
        capabilities: PlatformCapabilities,
    ) -> PortalRuntimeResult:
        needs_portal_wlan = _needs_portal_runtime(update, capabilities)
        needs_opennds_policy = capabilities.has_opennds and (
            update.portal_free_policy is not None
            or bool(update.portal_configs)
        )
        if not needs_portal_wlan and not needs_opennds_policy:
            return PortalRuntimeResult(applied=True, changed=False)
        if needs_portal_wlan and not capabilities.supports_portal:
            return PortalRuntimeResult(
                applied=False,
                error="portal requested but platform capability is disabled",
            )
        if capabilities.has_opennds:
            if not needs_opennds_policy:
                return PortalRuntimeResult(applied=True, changed=False)
            result = OpenNdsPortalAdapter(self._runner).apply(
                opennds_portal_policy_from_omada_config(
                    free_policy=update.portal_free_policy,
                    portal_configs=update.portal_configs,
                )
            )
            if not result.applied:
                return PortalRuntimeResult(applied=False, error=result.error)
            return PortalRuntimeResult(applied=True, changed=result.changed)
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


def _needs_portal_runtime(
    update: ApplyDeviceConfigurationCommand,
    capabilities: PlatformCapabilities,
) -> bool:
    wlans = update.wlans[: max(0, capabilities.max_ssids)]
    return any(wlan.portal.enabled for wlan in wlans)


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
