"""Host/platform capability detection for Omada AP features.

The ECSP component map says what the protocol handler can parse.  This module
answers a different question: what the local host can actually enforce.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Callable, Mapping

from ....application.contracts import PlatformCapabilities
from ....contexts.wireless.domain import RadioBand


CommandExists = Callable[[str], str | None]
CommandOutput = Callable[[tuple[str, ...]], str | None]


def detect_platform_capabilities(
    *,
    env: Mapping[str, str] | None = None,
    command_exists: CommandExists | None = None,
    command_output: CommandOutput | None = None,
) -> PlatformCapabilities:
    values = env if env is not None else os.environ
    which = command_exists or shutil.which

    platform = _platform(values)
    has_uci = which("uci") is not None
    has_ubus = which("ubus") is not None
    has_nft = which("nft") is not None
    has_hostapd = which("hostapd") is not None
    has_dnsmasq = which("dnsmasq") is not None
    has_opennds = which("opennds") is not None and which("ndsctl") is not None
    openwrt = platform == "openwrt" or (platform == "auto" and has_uci and has_ubus)

    radio_bands = _radio_bands(values.get("OMADA_RADIO_BANDS", "2g"))
    max_ssids = _int(values, "OMADA_MAX_SSIDS", 4)
    wlan_possible = openwrt and has_uci
    max_ssids = _cap_max_ssids_by_iw(
        max_ssids=max_ssids,
        openwrt=openwrt,
        command_exists=which,
        command_output=command_output or _run_command_output,
    )

    return PlatformCapabilities(
        platform="openwrt" if openwrt else platform,
        has_uci=has_uci,
        has_ubus=has_ubus,
        has_nft=has_nft,
        has_hostapd=has_hostapd,
        has_dnsmasq=has_dnsmasq,
        has_opennds=has_opennds,
        radio_bands=radio_bands,
        max_ssids=max(0, max_ssids),
        supports_wlan_config=_feature(values, "OMADA_CAP_WLAN", wlan_possible),
        supports_wpa2_psk=_feature(values, "OMADA_CAP_WPA2_PSK", wlan_possible),
        supports_wpa3_psk=_feature(values, "OMADA_CAP_WPA3_PSK", False),
        supports_wpa_enterprise=_feature(values, "OMADA_CAP_WPA_ENTERPRISE", False),
        supports_radius=_feature(values, "OMADA_CAP_RADIUS", False),
        supports_ssid_vlan=_feature(values, "OMADA_CAP_SSID_VLAN", False),
        supports_dynamic_vlan=_feature(values, "OMADA_CAP_DYNAMIC_VLAN", False),
        supports_management_vlan=_feature(values, "OMADA_CAP_MANAGEMENT_VLAN", False),
        supports_portal=_feature(values, "OMADA_CAP_PORTAL", openwrt and has_opennds),
        supports_dhcp_tracking=_feature(values, "OMADA_CAP_DHCP_TRACKING", openwrt and has_ubus),
        supports_option82=_feature(values, "OMADA_CAP_OPTION82", False),
        supports_led_control=_feature(
            values,
            "OMADA_CAP_LED",
            bool(
                values.get("OMADA_LED_BRIGHTNESS_PATH", "").strip()
                or values.get("OMADA_LED_TRIGGER_PATH", "").strip()
            ),
        ),
        supports_client_operations=_feature(
            values,
            "OMADA_CAP_CLIENT_OPERATIONS",
            openwrt and has_ubus,
        ),
        supports_client_rate_limits=_feature(values, "OMADA_CAP_CLIENT_RATE_LIMITS", False),
    )


def capability_summary(capabilities: PlatformCapabilities) -> str:
    bands = ",".join(band.value for band in capabilities.radio_bands) or "none"
    enabled = []
    for field in (
        "supports_wlan_config",
        "supports_wpa2_psk",
        "supports_wpa3_psk",
        "supports_wpa_enterprise",
        "supports_radius",
        "supports_ssid_vlan",
        "supports_dynamic_vlan",
        "supports_management_vlan",
        "supports_portal",
        "supports_dhcp_tracking",
        "supports_option82",
        "supports_led_control",
        "supports_client_operations",
        "supports_client_rate_limits",
    ):
        if getattr(capabilities, field):
            enabled.append(field.removeprefix("supports_"))
    features = ",".join(enabled) if enabled else "none"
    return (
        f"platform={capabilities.platform} bands={bands} maxSsids={capabilities.max_ssids} "
        f"tools=uci:{int(capabilities.has_uci)},ubus:{int(capabilities.has_ubus)},"
        f"nft:{int(capabilities.has_nft)},hostapd:{int(capabilities.has_hostapd)},"
        f"dnsmasq:{int(capabilities.has_dnsmasq)},opennds:{int(capabilities.has_opennds)} "
        f"features={features}"
    )


def _platform(env: Mapping[str, str]) -> str:
    value = env.get("OPENOMADA_PLATFORM", env.get("OMADA_PLATFORM", "auto")).strip().lower()
    if value not in {"auto", "openwrt", "generic", "genieacs"}:
        raise ValueError("OPENOMADA_PLATFORM/OMADA_PLATFORM must be auto, openwrt, generic or genieacs")
    return value


def _radio_bands(raw: str) -> tuple[RadioBand, ...]:
    bands = []
    for item in raw.split(","):
        value = item.strip().lower()
        if not value:
            continue
        try:
            bands.append(RadioBand(value))
        except ValueError as exc:
            raise ValueError(f"unsupported OMADA_RADIO_BANDS entry: {value}") from exc
    return tuple(dict.fromkeys(bands))


def _feature(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = env.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "enable", "enabled"}


def _int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw, 0)


def _cap_max_ssids_by_iw(
    *,
    max_ssids: int,
    openwrt: bool,
    command_exists: CommandExists,
    command_output: CommandOutput,
) -> int:
    configured = max(0, max_ssids)
    if not openwrt or configured <= 1:
        return configured

    iw = command_exists("iw")
    if iw is None:
        return configured

    detected = _iw_ap_interface_limit(command_output((iw, "list")) or "")
    if detected is None:
        return configured
    return min(configured, max(0, detected))


def _iw_ap_interface_limit(output: str) -> int | None:
    if "interface combinations are not supported" in output:
        return 1 if _iw_supports_ap_mode(output) else None

    limits = []
    for modes, limit in re.findall(r"#\{\s*([^}]*)\s*\}\s*<=\s*(\d+)", output):
        if any(mode.strip() == "AP" for mode in modes.split(",")):
            limits.append(int(limit))
    if not limits:
        return None
    return max(limits)


def _iw_supports_ap_mode(output: str) -> bool:
    for line in output.splitlines():
        if line.strip() == "* AP":
            return True
    return False


def _run_command_output(args: tuple[str, ...]) -> str | None:
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            check=False,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout
