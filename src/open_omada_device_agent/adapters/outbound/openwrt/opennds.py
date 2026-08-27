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
    landing_page_url: str | None = None
    default_ssid_name: str | None = None
    ap_mac: str | None = None
    site_id: str | None = None
    site_name: str | None = None


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
        commands.append(["uci", "set", "opennds.@opennds[0].allow_preemptive_authentication=0"])
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
    device_mac: str | None = None,
    site_id: str | None = None,
    site_name: str | None = None,
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
        landing_page_url=_portal_landing_page_url(portal_configs),
        default_ssid_name=_portal_default_ssid_name(portal_configs),
        ap_mac=_portal_ap_mac(config.MAC if device_mac is None else device_mac),
        site_id=_portal_site_id(
            portal_configs=portal_configs,
            configured_site_id=config.SITE_ID if site_id is None else site_id,
        ),
        site_name=_portal_site_name(
            portal_configs=portal_configs,
            configured_site_name=config.SITE_NAME if site_name is None else site_name,
        ),
    )


def build_openomada_redirect_themespec(policy: OpenNdsPortalPolicy) -> str:
    if not policy.portal_redirect_url:
        raise ValueError("openNDS Omada redirect ThemeSpec requires portal_redirect_url")
    portal_url = shlex.quote(policy.portal_redirect_url)
    landing_page_url = shlex.quote(policy.landing_page_url or "")
    default_ssid_name = shlex.quote(policy.default_ssid_name or "")
    ap_mac = shlex.quote(policy.ap_mac or "")
    site_id = shlex.quote(policy.site_id or "")
    site_name = shlex.quote(policy.site_name or "")
    safe_link = html.escape(policy.portal_redirect_url, quote=True)
    return "\n".join(
        (
            "#!/bin/sh",
            'title="openomada-controller-redirect"',
            f"openomada_portal_url={portal_url}",
            f"openomada_landing_page_url={landing_page_url}",
            f"openomada_default_ssid_name={default_ssid_name}",
            f"openomada_ap_mac={ap_mac}",
            f"openomada_site_id={site_id}",
            f"openomada_site_name={site_name}",
            "",
            "_openomada_hexdump() {",
            "    if [ -x /usr/bin/hexdump ]; then",
            "        /usr/bin/hexdump -v -e '1/1 \"%02x\"'",
            "    elif [ -x /bin/hexdump ]; then",
            "        /bin/hexdump -v -e '1/1 \"%02x\"'",
            "    elif command -v hexdump >/dev/null 2>&1; then",
            "        hexdump -v -e '1/1 \"%02x\"'",
            "    elif [ -x /bin/busybox ]; then",
            "        /bin/busybox hexdump -v -e '1/1 \"%02x\"'",
            "    else",
            "        return 1",
            "    fi",
            "}",
            "",
            "_openomada_urlencode() {",
            "    hex=$(printf \"%s\" \"$1\" | _openomada_hexdump 2>/dev/null)",
            "    encoded=\"\"",
            "    while [ -n \"$hex\" ]; do",
            "        byte=${hex%\"${hex#??}\"}",
            "        hex=${hex#??}",
            "        case \"$byte\" in",
            "            2d) encoded=\"${encoded}-\" ;;",
            "            2e) encoded=\"${encoded}.\" ;;",
            "            30) encoded=\"${encoded}0\" ;;",
            "            31) encoded=\"${encoded}1\" ;;",
            "            32) encoded=\"${encoded}2\" ;;",
            "            33) encoded=\"${encoded}3\" ;;",
            "            34) encoded=\"${encoded}4\" ;;",
            "            35) encoded=\"${encoded}5\" ;;",
            "            36) encoded=\"${encoded}6\" ;;",
            "            37) encoded=\"${encoded}7\" ;;",
            "            38) encoded=\"${encoded}8\" ;;",
            "            39) encoded=\"${encoded}9\" ;;",
            "            20) encoded=\"${encoded}+\" ;;",
            "            41) encoded=\"${encoded}A\" ;;",
            "            42) encoded=\"${encoded}B\" ;;",
            "            43) encoded=\"${encoded}C\" ;;",
            "            44) encoded=\"${encoded}D\" ;;",
            "            45) encoded=\"${encoded}E\" ;;",
            "            46) encoded=\"${encoded}F\" ;;",
            "            47) encoded=\"${encoded}G\" ;;",
            "            48) encoded=\"${encoded}H\" ;;",
            "            49) encoded=\"${encoded}I\" ;;",
            "            4a) encoded=\"${encoded}J\" ;;",
            "            4b) encoded=\"${encoded}K\" ;;",
            "            4c) encoded=\"${encoded}L\" ;;",
            "            4d) encoded=\"${encoded}M\" ;;",
            "            4e) encoded=\"${encoded}N\" ;;",
            "            4f) encoded=\"${encoded}O\" ;;",
            "            50) encoded=\"${encoded}P\" ;;",
            "            51) encoded=\"${encoded}Q\" ;;",
            "            52) encoded=\"${encoded}R\" ;;",
            "            53) encoded=\"${encoded}S\" ;;",
            "            54) encoded=\"${encoded}T\" ;;",
            "            55) encoded=\"${encoded}U\" ;;",
            "            56) encoded=\"${encoded}V\" ;;",
            "            57) encoded=\"${encoded}W\" ;;",
            "            58) encoded=\"${encoded}X\" ;;",
            "            59) encoded=\"${encoded}Y\" ;;",
            "            5a) encoded=\"${encoded}Z\" ;;",
            "            5f) encoded=\"${encoded}_\" ;;",
            "            61) encoded=\"${encoded}a\" ;;",
            "            62) encoded=\"${encoded}b\" ;;",
            "            63) encoded=\"${encoded}c\" ;;",
            "            64) encoded=\"${encoded}d\" ;;",
            "            65) encoded=\"${encoded}e\" ;;",
            "            66) encoded=\"${encoded}f\" ;;",
            "            67) encoded=\"${encoded}g\" ;;",
            "            68) encoded=\"${encoded}h\" ;;",
            "            69) encoded=\"${encoded}i\" ;;",
            "            6a) encoded=\"${encoded}j\" ;;",
            "            6b) encoded=\"${encoded}k\" ;;",
            "            6c) encoded=\"${encoded}l\" ;;",
            "            6d) encoded=\"${encoded}m\" ;;",
            "            6e) encoded=\"${encoded}n\" ;;",
            "            6f) encoded=\"${encoded}o\" ;;",
            "            70) encoded=\"${encoded}p\" ;;",
            "            71) encoded=\"${encoded}q\" ;;",
            "            72) encoded=\"${encoded}r\" ;;",
            "            73) encoded=\"${encoded}s\" ;;",
            "            74) encoded=\"${encoded}t\" ;;",
            "            75) encoded=\"${encoded}u\" ;;",
            "            76) encoded=\"${encoded}v\" ;;",
            "            77) encoded=\"${encoded}w\" ;;",
            "            78) encoded=\"${encoded}x\" ;;",
            "            79) encoded=\"${encoded}y\" ;;",
            "            7a) encoded=\"${encoded}z\" ;;",
            "            7e) encoded=\"${encoded}~\" ;;",
            "            *) encoded=\"${encoded}%$(printf \"%s\" \"$byte\" | tr 'a-f' 'A-F')\" ;;",
            "        esac",
            "    done",
            "    _openomada_normalize_encoded_hex_escapes \"$encoded\"",
            "}",
            "",
            "_openomada_normalize_encoded_hex_escapes() {",
            "    openomada_encoded_source=$1",
            "    openomada_encoded_normalized=\"\"",
            "    while [ -n \"$openomada_encoded_source\" ]; do",
            "        case \"$openomada_encoded_source\" in",
            "            %5Cx[0-9A-Fa-f][0-9A-Fa-f]*)",
            "                openomada_hex_escape_rest=${openomada_encoded_source#%5Cx}",
            "                openomada_hex_escape_pair=${openomada_hex_escape_rest%\"${openomada_hex_escape_rest#??}\"}",
            "                openomada_encoded_source=${openomada_hex_escape_rest#??}",
            "                openomada_encoded_normalized=\"${openomada_encoded_normalized}%$(printf \"%s\" \"$openomada_hex_escape_pair\" | tr 'a-f' 'A-F')\"",
            "                ;;",
            "            %5CX[0-9A-Fa-f][0-9A-Fa-f]*)",
            "                openomada_hex_escape_rest=${openomada_encoded_source#%5CX}",
            "                openomada_hex_escape_pair=${openomada_hex_escape_rest%\"${openomada_hex_escape_rest#??}\"}",
            "                openomada_encoded_source=${openomada_hex_escape_rest#??}",
            "                openomada_encoded_normalized=\"${openomada_encoded_normalized}%$(printf \"%s\" \"$openomada_hex_escape_pair\" | tr 'a-f' 'A-F')\"",
            "                ;;",
            "            *)",
            "                openomada_encoded_char=${openomada_encoded_source%\"${openomada_encoded_source#?}\"}",
            "                openomada_encoded_source=${openomada_encoded_source#?}",
            "                openomada_encoded_normalized=\"${openomada_encoded_normalized}${openomada_encoded_char}\"",
            "                ;;",
            "        esac",
            "    done",
            "    printf \"%s\" \"$openomada_encoded_normalized\"",
            "}",
            "",
            "_openomada_urldecode() {",
            "    value=$(printf \"%s\" \"$1\" | sed 's/+/ /g; s/%/\\\\x/g')",
            "    printf \"%b\" \"$value\"",
            "}",
            "",
            "_openomada_html_unescape_url() {",
            "    printf \"%s\" \"$1\" | sed 's|&#47;|/|g; s|&#x2[fF];|/|g; s|&#58;|:|g; s|&#x3[aA];|:|g; s|&amp;|\\&|g'",
            "}",
            "",
            "_openomada_backslash_unescape() {",
            "    printf \"%b\" \"$1\"",
            "}",
            "",
            "_openomada_append_param() {",
            "    key=$1",
            "    value=$2",
            "    case \"$openomada_target\" in",
            "        *\\?|*\\&) sep=\"\" ;;",
            "        *\\?*) sep=\"&\" ;;",
            "        *) sep=\"?\" ;;",
            "    esac",
            "    openomada_target=\"${openomada_target}${sep}${key}=$(_openomada_urlencode \"$value\")\"",
            "}",
            "",
            "_openomada_format_mac() {",
            "    printf \"%s\" \"$1\" | tr 'a-f:' 'A-F-'",
            "}",
            "",
            "_openomada_iface_address() {",
            "    iface=$1",
            "    [ -n \"$iface\" ] || return",
            "    [ -r \"/sys/class/net/$iface/address\" ] || return",
            "    read -r mac < \"/sys/class/net/$iface/address\" || return",
            "    printf \"%s\" \"$mac\" | tr 'A-F' 'a-f'",
            "}",
            "",
            "_openomada_ssid_from_iw() {",
            "    iface=$1",
            "    [ -n \"$iface\" ] || return",
            "    command -v iw >/dev/null 2>&1 || return",
            "    iw dev \"$iface\" info 2>/dev/null | awk '",
            "        /^[ \\t]*ssid[ \\t]+/ {",
            "            sub(/^[ \\t]*ssid[ \\t]+/, \"\")",
            "            print",
            "            exit",
            "        }",
            "    '",
            "}",
            "",
            "_openomada_radio_id_from_iw() {",
            "    iface=$1",
            "    [ -n \"$iface\" ] || return",
            "    command -v iw >/dev/null 2>&1 || return",
            "    freq=$(iw dev \"$iface\" info 2>/dev/null | awk '",
            "        /^[ \\t]*channel[ \\t]+/ {",
            "            for (i = 1; i <= NF; i++) {",
            "                if ($i ~ /^\\([0-9]+$/) {",
            "                    gsub(/[()]/, \"\", $i)",
            "                    print $i",
            "                    exit",
            "                }",
            "            }",
            "        }",
            "    ')",
            "    case \"$freq\" in",
            "        ''|*[!0-9]*) ;;",
            "        *)",
            "            if [ \"$freq\" -lt 3000 ]; then",
            "                printf \"0\"",
            "            elif [ \"$freq\" -ge 5925 ]; then",
            "                printf \"3\"",
            "            else",
            "                printf \"1\"",
            "            fi",
            "            return",
            "            ;;",
            "    esac",
            "    channel=$(iw dev \"$iface\" info 2>/dev/null | awk '/^[ \\t]*channel[ \\t]+/ { print $2; exit }')",
            "    case \"$channel\" in",
            "        ''|*[!0-9]*) return ;;",
            "    esac",
            "    if [ \"$channel\" -le 14 ]; then",
            "        printf \"0\"",
            "    else",
            "        printf \"1\"",
            "    fi",
            "}",
            "",
            "_openomada_now() {",
            "    date +%s 2>/dev/null || printf \"0\"",
            "}",
            "",
            "generate_splash_sequence() {",
            "    openomada_target=$openomada_portal_url",
            "    openomada_client_mac=$(_openomada_format_mac \"${clientmac:-}\")",
            "    openomada_client_ip=${clientip:-}",
            "    openomada_client_if=${clientif:-}",
            "    openomada_resolved_ap_mac=${openomada_ap_mac:-}",
            "    if [ -z \"$openomada_resolved_ap_mac\" ]; then",
            "        openomada_resolved_ap_mac=$(_openomada_iface_address \"$openomada_client_if\")",
            "    fi",
            "    openomada_resolved_ap_mac=$(_openomada_format_mac \"$openomada_resolved_ap_mac\")",
            "    openomada_site_ref=${openomada_site_id:-$openomada_site_name}",
            "    openomada_resolved_ssid=${openomada_default_ssid_name:-}",
            "    if [ -z \"$openomada_resolved_ssid\" ]; then",
            "        openomada_resolved_ssid=$(_openomada_ssid_from_iw \"$openomada_client_if\")",
            "    fi",
            "    if [ -z \"$openomada_resolved_ssid\" ]; then",
            "        openomada_resolved_ssid=${client_zone:-}",
            "    fi",
            "    if [ -n \"$openomada_resolved_ssid\" ]; then",
            "        openomada_resolved_ssid=$(_openomada_backslash_unescape \"$openomada_resolved_ssid\")",
            "    fi",
            "    openomada_radio_id=$(_openomada_radio_id_from_iw \"$openomada_client_if\")",
            "    if [ -z \"$openomada_radio_id\" ]; then",
            "        openomada_radio_id=\"0\"",
            "    fi",
            "    openomada_redirect_url=$openomada_landing_page_url",
            "    if [ -z \"$openomada_redirect_url\" ] && [ -n \"${originurl:-}\" ]; then",
            "        openomada_redirect_url=$(_openomada_urldecode \"$originurl\")",
            "        openomada_redirect_url=$(_openomada_html_unescape_url \"$openomada_redirect_url\")",
            "    fi",
            "    _openomada_append_param \"clientMac\" \"$openomada_client_mac\"",
            "    _openomada_append_param \"clientIp\" \"$openomada_client_ip\"",
            "    _openomada_append_param \"t\" \"$(_openomada_now)\"",
            "    _openomada_append_param \"site\" \"$openomada_site_ref\"",
            "    _openomada_append_param \"redirectUrl\" \"$openomada_redirect_url\"",
            "    _openomada_append_param \"apMac\" \"$openomada_resolved_ap_mac\"",
            "    _openomada_append_param \"ssidName\" \"$openomada_resolved_ssid\"",
            "    _openomada_append_param \"radioId\" \"$openomada_radio_id\"",
            "    safe_target=$(printf \"%s\" \"$openomada_target\" | sed 's/&/\\&amp;/g; s/\"/\\&quot;/g; s/</\\&lt;/g; s/>/\\&gt;/g')",
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
            f"# Static portal base URL: {safe_link}",
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
    for portal_config in portal_configs:
        normalized = _normal_portal_url(
            portal_config.redirect_url if portal_config.redirect is not False else None
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


def _portal_landing_page_url(portal_configs: tuple[PortalConfiguration, ...]) -> str | None:
    for portal_config in portal_configs:
        if portal_config.redirect is False:
            continue
        normalized = _normal_portal_url(portal_config.redirect_url)
        if normalized is not None:
            return normalized
    return None


def _portal_default_ssid_name(portal_configs: tuple[PortalConfiguration, ...]) -> str | None:
    for portal_config in portal_configs:
        for ssid in portal_config.ssid_list:
            normalized = str(ssid).strip()
            if normalized:
                return normalized
    return None


def _portal_ap_mac(value: object) -> str | None:
    try:
        return MacAddress(str(value)).omada
    except ValueError:
        return None


def _portal_site_id(
    *,
    portal_configs: tuple[PortalConfiguration, ...],
    configured_site_id: str,
) -> str | None:
    for portal_config in portal_configs:
        normalized = (portal_config.site_id or "").strip()
        if normalized:
            return normalized
    normalized = configured_site_id.strip()
    return normalized or None


def _portal_site_name(
    *,
    portal_configs: tuple[PortalConfiguration, ...],
    configured_site_name: str,
) -> str | None:
    for portal_config in portal_configs:
        normalized = (portal_config.site_name or "").strip()
        if normalized:
            return normalized
    normalized = configured_site_name.strip()
    return normalized or None


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
