"""openNDS integration for captive portal state observations."""
from __future__ import annotations

import json
import ipaddress
import html
import shlex
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from .... import config
from ....contexts.portal.domain import PortalConfiguration, PortalFreePolicy
from ....contexts.clients.domain import ClientPortalState, WirelessClientState
from ....shared.domain import MacAddress
from .uci import CommandRunner, SubprocessRunner
from ....application.contracts import PlatformCapabilities
from .capabilities import detect_platform_capabilities


OPENNDS_STATE_MAP = {
    "authenticated": ClientPortalState.AUTHENTICATED,
    "trusted": ClientPortalState.AUTHENTICATED,
    "preauthenticated": ClientPortalState.UNAUTHENTICATED,
    "preauth": ClientPortalState.UNAUTHENTICATED,
    "blocked": ClientPortalState.BLOCKED,
}


OPENOMADA_THEMESPEC_PATH = "/usr/lib/opennds/theme_openomada_redirect.sh"


@dataclass(frozen=True)
class OpenNdsPortalPolicy:
    walled_garden_fqdns: tuple[str, ...] = ()
    preauthenticated_user_rules: tuple[str, ...] = ()
    walled_garden_ports: tuple[int, ...] = (80, 443, 8088, 8843)
    portal_redirect_url: str | None = None


@dataclass(frozen=True)
class OpenNdsPortalResult:
    applied: bool
    changed: bool = False
    error: str = ""


class OpenNdsPortalAdapter:
    def __init__(self, runner: CommandRunner | None = None) -> None:
        self._runner = runner or SubprocessRunner()

    def apply(self, policy: OpenNdsPortalPolicy) -> OpenNdsPortalResult:
        delete_commands = [
            ["uci", "-q", "delete", "opennds.@opennds[0].walledgarden_fqdn_list"],
            ["uci", "-q", "delete", "opennds.@opennds[0].walledgarden_port_list"],
            ["uci", "-q", "delete", "opennds.@opennds[0].preauthenticated_users"],
            ["uci", "-q", "delete", "opennds.@opennds[0].themespec_path"],
        ]
        commands = []
        commands.extend(
            [
                "uci",
                "add_list",
                f"opennds.@opennds[0].walledgarden_fqdn_list={fqdn}",
            ]
            for fqdn in policy.walled_garden_fqdns
        )
        if policy.walled_garden_fqdns:
            ports = " ".join(str(port) for port in policy.walled_garden_ports)
            commands.append(
                [
                    "uci",
                    "add_list",
                    f"opennds.@opennds[0].walledgarden_port_list={ports}",
                ]
            )
        commands.extend(
            [
                "uci",
                "add_list",
                f"opennds.@opennds[0].preauthenticated_users={rule}",
            ]
            for rule in policy.preauthenticated_user_rules
        )
        if policy.portal_redirect_url:
            write_result = self._runner.run(
                ["tee", OPENOMADA_THEMESPEC_PATH],
                input_text=build_openomada_redirect_themespec(policy),
            )
            if write_result.returncode != 0:
                return OpenNdsPortalResult(
                    applied=False,
                    error=(
                        write_result.stderr
                        or write_result.stdout
                        or "openNDS ThemeSpec write failed"
                    ).strip(),
                )
            chmod_result = self._runner.run(["chmod", "0644", OPENOMADA_THEMESPEC_PATH])
            if chmod_result.returncode != 0:
                return OpenNdsPortalResult(
                    applied=False,
                    error=(
                        chmod_result.stderr
                        or chmod_result.stdout
                        or "openNDS ThemeSpec chmod failed"
                    ).strip(),
                )
            commands.append(["uci", "set", "opennds.@opennds[0].login_option_enabled=3"])
            commands.append(
                [
                    "uci",
                    "set",
                    f"opennds.@opennds[0].themespec_path={OPENOMADA_THEMESPEC_PATH}",
                ]
            )
        else:
            commands.append(["uci", "set", "opennds.@opennds[0].login_option_enabled=1"])
        commands.append(["uci", "commit", "opennds"])
        commands.append(["/etc/init.d/opennds", "restart"])

        for command in delete_commands:
            self._runner.run(command)
        for command in commands:
            result = self._runner.run(command)
            if result.returncode != 0:
                return OpenNdsPortalResult(
                    applied=False,
                    error=(result.stderr or result.stdout or f"{command[0]} failed").strip(),
                )
        return OpenNdsPortalResult(applied=True, changed=True)


class OpenNdsClientTelemetry:
    def __init__(self, runner: CommandRunner | None = None) -> None:
        self._runner = runner or SubprocessRunner()

    def collect(self) -> tuple[WirelessClientState, ...]:
        try:
            result = self._runner.run(["ndsctl", "json"])
        except OSError:
            return ()
        if result.returncode != 0 or not result.stdout.strip():
            return ()
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            return ()
        if not isinstance(payload, Mapping):
            return ()
        return opennds_clients_from_json(payload)


def collect_opennds_clients(
    *,
    capabilities: PlatformCapabilities | None = None,
    runner: CommandRunner | None = None,
) -> tuple[WirelessClientState, ...]:
    detected = capabilities or detect_platform_capabilities()
    if detected.platform != "openwrt" or not detected.has_opennds:
        return ()
    return OpenNdsClientTelemetry(runner).collect()


def opennds_clients_from_json(payload: Mapping[str, Any]) -> tuple[WirelessClientState, ...]:
    raw_clients = payload.get("clients")
    if not isinstance(raw_clients, Mapping):
        return ()

    clients: list[WirelessClientState] = []
    for raw_mac, raw_client in raw_clients.items():
        if not isinstance(raw_client, Mapping):
            continue
        mac = _mac(raw_client.get("mac"), raw_mac)
        if mac is None:
            continue
        clients.append(
            WirelessClientState(
                mac=mac,
                ipv4=_optional_str(raw_client.get("ip")),
                portal_state=_portal_state(raw_client.get("state")),
                rx_bytes=_optional_int(raw_client.get("download_this_session")) or 0,
                tx_bytes=_optional_int(raw_client.get("upload_this_session")) or 0,
            )
        )
    return tuple(sorted(clients, key=lambda client: client.mac))


def opennds_portal_policy_from_free_policy(
    policy: PortalFreePolicy | None,
) -> OpenNdsPortalPolicy:
    if policy is None:
        return OpenNdsPortalPolicy()
    return OpenNdsPortalPolicy(
        walled_garden_fqdns=_portal_free_policy_fqdns(policy),
        preauthenticated_user_rules=_portal_free_policy_preauth_rules(policy),
    )


def opennds_portal_policy_from_omada_config(
    *,
    free_policy: PortalFreePolicy | None,
    portal_configs: tuple[PortalConfiguration, ...] = (),
    controller_host: str | None = None,
) -> OpenNdsPortalPolicy:
    base = opennds_portal_policy_from_free_policy(free_policy)
    return OpenNdsPortalPolicy(
        walled_garden_fqdns=base.walled_garden_fqdns,
        preauthenticated_user_rules=base.preauthenticated_user_rules,
        walled_garden_ports=base.walled_garden_ports,
        portal_redirect_url=_portal_redirect_url(
            free_policy=free_policy,
            portal_configs=portal_configs,
            controller_host=config.CONTROLLER_HOST if controller_host is None else controller_host,
        ),
    )


def build_openomada_redirect_themespec(policy: OpenNdsPortalPolicy) -> str:
    if not policy.portal_redirect_url:
        raise ValueError("openNDS Omada redirect ThemeSpec requires portal_redirect_url")
    portal_url = shlex.quote(policy.portal_redirect_url)
    safe_link = html.escape(policy.portal_redirect_url, quote=True)
    return "\n".join(
        (
            "#!/bin/sh",
            'title="openomada-controller-redirect"',
            f"openomada_portal_url={portal_url}",
            "",
            "generate_splash_sequence() {",
            '    safe_target=$(printf "%s" "$openomada_portal_url" | sed "s/&/\\\\&amp;/g; s/\\"/\\\\&quot;/g; s/</\\\\&lt;/g; s/>/\\\\&gt;/g")',
            '    echo "<meta http-equiv=\\"refresh\\" content=\\"0; url=$safe_target\\">"',
            '    echo "<p><a href=\\"$safe_target\\">Open Omada portal</a></p>"',
            "}",
            "",
            "header() {",
            '    echo "<!DOCTYPE html><html><head><meta charset=\\"utf-8\\"><meta name=\\"viewport\\" content=\\"width=device-width, initial-scale=1.0\\"><title>Omada Portal</title></head><body>"',
            "}",
            "",
            "footer() {",
            '    echo "</body></html>"',
            "    exit 0",
            "}",
            "",
            f"# Static fallback link: {safe_link}",
            "",
        )
    )


def _portal_free_policy_fqdns(policy: PortalFreePolicy) -> tuple[str, ...]:
    fqdns = []
    for rule in _iter_rules(policy.url_rules):
        host = _host_from_rule(rule)
        if host is not None:
            fqdns.append(host)
    return tuple(dict.fromkeys(fqdns))


def _portal_free_policy_preauth_rules(policy: PortalFreePolicy) -> tuple[str, ...]:
    rules = []
    for raw_rule in _iter_rules(policy.layer2_rules):
        if target := _network_from_rule(raw_rule):
            rules.append(f"allow all to {target}")
    return tuple(dict.fromkeys(rules))


def _portal_redirect_url(
    *,
    free_policy: PortalFreePolicy | None,
    portal_configs: tuple[PortalConfiguration, ...],
    controller_host: str,
) -> str | None:
    for portal_config in portal_configs:
        for raw_url in (
            portal_config.external_portal_server,
            portal_config.ext_auth_server,
            portal_config.redirect_url if portal_config.redirect is not False else None,
        ):
            normalized = _normal_portal_url(raw_url)
            if normalized is not None:
                return normalized
    if free_policy is not None:
        for rule in _iter_rules(free_policy.url_rules):
            normalized = _normal_portal_url(
                rule.get("url") or rule.get("host") or rule.get("value"),
                require_portal_path=True,
            )
            if normalized is not None:
                return normalized
    host = (controller_host or "").strip()
    if not host:
        return None
    parsed = urlparse(host if "://" in host else f"//{host}")
    hostname = parsed.hostname
    if not hostname:
        return None
    scheme = parsed.scheme or "http"
    port = parsed.port or (8843 if scheme == "https" else 8088)
    return f"{scheme}://{hostname}:{port}/portal/entry"


def _normal_portal_url(
    value: object,
    *,
    require_portal_path: bool = False,
) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    path = parsed.path or ""
    if require_portal_path and "portal" not in path.lower():
        return None
    return parsed.geturl()


def _iter_rules(rules: tuple[Mapping[str, Any], ...]) -> tuple[Mapping[str, Any], ...]:
    collected: list[Mapping[str, Any]] = []
    for rule in rules:
        collected.append(rule)
        raw_children = rule.get("children") or rule.get("entries") or ()
        if isinstance(raw_children, tuple | list):
            collected.extend(
                child for child in raw_children if isinstance(child, Mapping)
            )
    return tuple(collected)


def _host_from_rule(rule: Mapping[str, Any]) -> str | None:
    raw = rule.get("url") or rule.get("host") or rule.get("value")
    if raw is None:
        return None
    value = str(raw).strip()
    if not value:
        return None
    parsed = urlparse(value if "://" in value else f"//{value}")
    host = (parsed.hostname or "").strip(".").lower()
    if not host:
        return None
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return host
    return None


def _network_from_rule(rule: Mapping[str, Any]) -> str | None:
    raw = rule.get("dstIp") or rule.get("value") or rule.get("ip") or rule.get("address")
    if raw is None:
        return None
    mask = rule.get("dstMask") or rule.get("mask")
    try:
        if mask is not None:
            return str(ipaddress.ip_network(f"{raw}/{mask}", strict=False))
        address = ipaddress.ip_address(str(raw))
    except ValueError:
        return None
    if address.version != 4:
        return None
    return str(address)


def _mac(*values: object) -> str | None:
    for value in values:
        if value is None:
            continue
        try:
            return MacAddress(str(value)).value
        except ValueError:
            continue
    return None


def _portal_state(value: object) -> ClientPortalState:
    if value is None:
        return ClientPortalState.UNKNOWN
    return OPENNDS_STATE_MAP.get(
        str(value).strip().lower(),
        ClientPortalState.UNKNOWN,
    )


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return max(0, int(float(str(value))))
    except ValueError:
        return None
