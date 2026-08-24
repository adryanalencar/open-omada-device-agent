"""OpenWrt platform adapter for AP WLAN configuration.

This module is deliberately below the Omada domain layer.  ECSP parsers produce
domain objects; this adapter turns supported domain objects into UCI changes.
"""
from __future__ import annotations

import re
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from .domain import AccessPointConfigUpdate, RadioBand, RadioConfig, WirelessNetwork
from .platform_capabilities import PlatformCapabilities


class CommandRunner(Protocol):
    def run(self, args: Sequence[str], *, input_text: str | None = None) -> "CommandResult":
        ...


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class ReconciliationResult:
    applied: bool
    changed: bool
    error: str = ""
    command_count: int = 0


class SubprocessRunner:
    def run(self, args: Sequence[str], *, input_text: str | None = None) -> CommandResult:
        completed = subprocess.run(
            list(args),
            input=input_text,
            text=True,
            capture_output=True,
            check=False,
        )
        return CommandResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


class OpenWrtUciAdapter:
    def __init__(self, runner: CommandRunner | None = None) -> None:
        self._runner = runner or SubprocessRunner()

    def reconcile(
        self,
        update: AccessPointConfigUpdate,
        capabilities: PlatformCapabilities,
    ) -> ReconciliationResult:
        errors = validate_update(update, capabilities)
        if errors:
            return ReconciliationResult(
                applied=False,
                changed=False,
                error="; ".join(errors),
            )

        batch = build_uci_batch(update, capabilities)
        if not batch:
            return ReconciliationResult(applied=True, changed=False)

        result = self._runner.run(["uci", "-q", "batch"], input_text="\n".join(batch) + "\n")
        if result.returncode != 0:
            return ReconciliationResult(
                applied=False,
                changed=False,
                error=(result.stderr or result.stdout or "uci batch failed").strip(),
                command_count=len(batch),
            )

        reload_result = self._runner.run(["wifi", "reload"])
        if reload_result.returncode != 0:
            return ReconciliationResult(
                applied=False,
                changed=True,
                error=(reload_result.stderr or reload_result.stdout or "wifi reload failed").strip(),
                command_count=len(batch),
            )

        return ReconciliationResult(applied=True, changed=True, command_count=len(batch))


def validate_update(
    update: AccessPointConfigUpdate,
    capabilities: PlatformCapabilities,
) -> tuple[str, ...]:
    errors: list[str] = []
    if (update.radios or update.wlans) and not capabilities.supports_wlan_config:
        errors.append("platform does not support WLAN configuration")
    if len(update.wlans) > capabilities.max_ssids:
        errors.append(
            f"controller requested {len(update.wlans)} SSIDs but platform max is {capabilities.max_ssids}"
        )
    for radio in update.radios:
        if radio.band not in capabilities.radio_bands:
            errors.append(f"radio band {radio.band.value} is not supported")
    for wlan in update.wlans:
        if wlan.band not in capabilities.radio_bands:
            errors.append(f"SSID band {wlan.band.value} is not supported")
        if wlan.vlan.vlan_id is not None and not capabilities.supports_ssid_vlan:
            errors.append("SSID VLAN requested but platform capability is disabled")
        if (
            wlan.vlan.dynamic_vlan_mode is not None
            and wlan.vlan.dynamic_vlan_mode != 0
            and not capabilities.supports_dynamic_vlan
        ):
            errors.append("dynamic VLAN requested but platform capability is disabled")
        if (
            wlan.vlan.dhcp_option82 is not None
            and wlan.vlan.dhcp_option82.enabled
            and not capabilities.supports_option82
        ):
            errors.append("DHCP Option 82 requested but platform capability is disabled")
        if wlan.portal.enabled and not capabilities.supports_portal:
            errors.append("portal WLAN requested but platform capability is disabled")
        if wlan.security.psk_key is not None and not capabilities.supports_wpa2_psk:
            errors.append("PSK WLAN requested but WPA2-PSK capability is disabled")
        if (
            wlan.security.radius_auth is not None
            or wlan.security.radius_accounting is not None
            or wlan.security.radius_mac_auth is not None
        ) and not capabilities.supports_radius:
            errors.append("RADIUS WLAN requested but RADIUS capability is disabled")
    if (
        update.management_vlan is not None
        and update.management_vlan.enabled
        and not capabilities.supports_management_vlan
    ):
        errors.append("management VLAN requested but platform capability is disabled")
    if update.portal_free_policy is not None:
        errors.append("portal free policy reconciliation is not implemented")
    return tuple(dict.fromkeys(errors))


def build_uci_batch(
    update: AccessPointConfigUpdate,
    capabilities: PlatformCapabilities,
) -> tuple[str, ...]:
    lines: list[str] = []
    vlan_ids = sorted(
        {
            wlan.vlan.vlan_id
            for wlan in update.wlans
            if wlan.vlan.vlan_id is not None and capabilities.supports_ssid_vlan
        }
    )
    for vlan_id in vlan_ids:
        lines.extend(_ssid_vlan_lines(vlan_id))
    if vlan_ids:
        lines.append("commit network")
    for radio in update.radios:
        lines.extend(_radio_lines(radio))
    for wlan in update.wlans:
        lines.extend(_wlan_lines(wlan, capabilities))
    if lines:
        lines.append("commit wireless")
    return tuple(lines)


def _radio_lines(radio: RadioConfig) -> tuple[str, ...]:
    section = _radio_section(radio.band, radio.radio_id)
    lines = []
    if radio.enabled is not None:
        lines.append(_set("wireless", section, "disabled", "0" if radio.enabled else "1"))
    if radio.channel is not None:
        lines.append(_set("wireless", section, "channel", str(radio.channel)))
    if radio.channel_width is not None:
        lines.append(_set("wireless", section, "htmode", _channel_width_mode(radio.channel_width)))
    if radio.tx_power is not None:
        lines.append(_set("wireless", section, "txpower", str(radio.tx_power)))
    return tuple(lines)


def _wlan_lines(wlan: WirelessNetwork, capabilities: PlatformCapabilities) -> tuple[str, ...]:
    section = _wlan_section(wlan)
    device = _radio_section(wlan.band, wlan.radio_id)
    network = "lan"
    if wlan.vlan.vlan_id is not None and capabilities.supports_ssid_vlan:
        network = f"openomada_vlan{wlan.vlan.vlan_id}"

    lines = [
        f"delete wireless.{section}",
        f"set wireless.{section}=wifi-iface",
        _set("wireless", section, "openomada_managed", "1"),
        _set("wireless", section, "device", device),
        _set("wireless", section, "mode", "ap"),
        _set("wireless", section, "network", network),
        _set("wireless", section, "ssid", wlan.name),
        _set("wireless", section, "hidden", "0" if wlan.broadcast is not False else "1"),
    ]
    if wlan.client_isolation is not None:
        lines.append(_set("wireless", section, "isolate", "1" if wlan.client_isolation else "0"))

    psk_key = wlan.security.psk_key
    if psk_key is not None:
        encryption = "sae-mixed" if wlan.security.psk_version == 3 else "psk2"
        lines.append(_set("wireless", section, "encryption", encryption))
        lines.append(_set("wireless", section, "key", psk_key.reveal()))
    else:
        lines.append(_set("wireless", section, "encryption", "none"))
    return tuple(lines)


def _ssid_vlan_lines(vlan_id: int) -> tuple[str, ...]:
    section = f"openomada_vlan{vlan_id}"
    return (
        f"delete network.{section}",
        f"set network.{section}=interface",
        _set("network", section, "proto", "none"),
        _set("network", section, "device", f"br-lan.{vlan_id}"),
    )


def _radio_section(band: RadioBand, radio_id: int | None) -> str:
    if radio_id is not None:
        return f"radio{radio_id}"
    return {
        RadioBand.TWO_G: "radio0",
        RadioBand.FIVE_G: "radio1",
        RadioBand.FIVE_G2: "radio2",
        RadioBand.SIX_G: "radio3",
    }[band]


def _wlan_section(wlan: WirelessNetwork) -> str:
    suffix = wlan.index if wlan.index is not None else wlan.ssid_id
    if suffix is None:
        suffix = _slug(wlan.name) or "ssid"
    return _slug(f"openomada_{wlan.band.value}_{suffix}")[:48]


def _channel_width_mode(width: int) -> str:
    if width <= 20:
        return "HT20"
    if width <= 40:
        return "HT40"
    if width <= 80:
        return "VHT80"
    return f"HE{width}"


def _set(config: str, section: str, option: str, value: str) -> str:
    return f"set {config}.{section}.{option}='{_uci_quote(value)}'"


def _uci_quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "'\\''")


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", value).strip("_").lower()
