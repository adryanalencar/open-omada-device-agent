"""Platform telemetry mapped to Omada AP inform keys."""
from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .domain import RadioBand
from .openwrt import CommandRunner, SubprocessRunner
from .platform_capabilities import PlatformCapabilities, detect_platform_capabilities

INFORM_SUFFIX_BY_BAND = {
    RadioBand.TWO_G: "2G",
    RadioBand.FIVE_G: "5G",
    RadioBand.FIVE_G2: "5G2",
    RadioBand.SIX_G: "6G",
}


class OpenWrtWirelessTelemetry:
    def __init__(self, runner: CommandRunner | None = None) -> None:
        self._runner = runner or SubprocessRunner()

    def collect(self) -> dict[str, object]:
        try:
            result = self._runner.run(["ubus", "call", "network.wireless", "status"])
        except OSError:
            return {}
        if result.returncode != 0 or not result.stdout.strip():
            return {}
        try:
            status = json.loads(result.stdout)
        except json.JSONDecodeError:
            return {}
        if not isinstance(status, Mapping):
            return {}
        return openwrt_wireless_inform_from_status(status)


def collect_openwrt_wireless_inform(
    *,
    capabilities: PlatformCapabilities | None = None,
    runner: CommandRunner | None = None,
) -> dict[str, object]:
    detected = capabilities or detect_platform_capabilities()
    if detected.platform != "openwrt" or not detected.has_ubus:
        return {}
    return OpenWrtWirelessTelemetry(runner).collect()


def openwrt_wireless_inform_from_status(status: Mapping[str, Any]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for radio_name, raw_radio in status.items():
        if not isinstance(raw_radio, Mapping):
            continue
        band = _band_from_radio_name(str(radio_name))
        if band is None:
            continue
        suffix = INFORM_SUFFIX_BY_BAND[band]
        interfaces = _interfaces(raw_radio.get("interfaces"))
        wireless_info = _wireless_info(raw_radio, interfaces)
        if wireless_info:
            payload[f"wSettings_{suffix}"] = wireless_info
        ssid_stats = tuple(
            stats
            for interface in interfaces
            if (stats := _ssid_stats(interface)) is not None
        )
        if ssid_stats:
            payload[f"ssidStats_{suffix}"] = list(ssid_stats)
    return payload


def _wireless_info(
    radio: Mapping[str, Any],
    interfaces: tuple[Mapping[str, Any], ...],
) -> dict[str, object]:
    config = _mapping(radio.get("config"))
    info: dict[str, object] = {}
    channel = config.get("channel") or radio.get("channel")
    if channel not in (None, ""):
        info["ch"] = str(channel)
    band_width = config.get("htmode") or config.get("bandwidth") or radio.get("htmode")
    if band_width not in (None, ""):
        info["bw"] = str(band_width)
    radio_mode = config.get("hwmode") or config.get("mode") or radio.get("hwmode")
    if radio_mode not in (None, ""):
        info["rdMode"] = str(radio_mode)
    tx_power = config.get("txpower") or radio.get("txpower")
    if tx_power not in (None, ""):
        info["txPower"] = str(tx_power)
    station_total = sum(_station_count(interface) for interface in interfaces)
    if station_total:
        info["staNum"] = station_total
    return info


def _ssid_stats(interface: Mapping[str, Any]) -> dict[str, object] | None:
    config = _mapping(interface.get("config"))
    ssid = config.get("ssid") or interface.get("ssid")
    if not ssid:
        return None
    stats: dict[str, object] = {
        "ssid": str(ssid),
        "clntNum": _station_count(interface),
    }
    bssid = interface.get("bssid") or config.get("bssid") or config.get("macaddr")
    if bssid:
        stats["bssid"] = str(bssid)
    counters = _mapping(interface.get("statistics") or interface.get("stats"))
    if counters:
        # Omada names traffic from AP perspective: tx is downlink to the client,
        # rx is uplink from the client.
        _copy_counter(stats, "down", counters, "tx_bytes", "txByte", "tx")
        _copy_counter(stats, "up", counters, "rx_bytes", "rxByte", "rx")
        _copy_counter(stats, "downPkts", counters, "tx_packets", "txPackets", "txP")
        _copy_counter(stats, "upPkts", counters, "rx_packets", "rxPackets", "rxP")
    return stats


def _interfaces(raw: Any) -> tuple[Mapping[str, Any], ...]:
    if isinstance(raw, Mapping):
        values = raw.values()
    elif isinstance(raw, list | tuple):
        values = raw
    else:
        return ()
    return tuple(item for item in values if isinstance(item, Mapping))


def _station_count(interface: Mapping[str, Any]) -> int:
    for key in ("stations", "assoclist", "clients"):
        raw = interface.get(key)
        if isinstance(raw, Mapping | list | tuple):
            return len(raw)
    for key in ("num_sta", "staNum"):
        raw = interface.get(key)
        if raw is not None:
            try:
                return max(0, int(raw))
            except (TypeError, ValueError):
                return 0
    return 0


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _copy_counter(
    target: dict[str, object],
    target_key: str,
    source: Mapping[str, Any],
    *source_keys: str,
) -> None:
    for key in source_keys:
        value = source.get(key)
        if value is None:
            continue
        try:
            target[target_key] = max(0, int(value))
        except (TypeError, ValueError):
            continue
        return


def _band_from_radio_name(name: str) -> RadioBand | None:
    normalized = name.strip().lower()
    if normalized in {"radio0", "2g", "2g4"}:
        return RadioBand.TWO_G
    if normalized in {"radio1", "5g"}:
        return RadioBand.FIVE_G
    if normalized in {"radio2", "5g2"}:
        return RadioBand.FIVE_G2
    if normalized in {"radio3", "6g"}:
        return RadioBand.SIX_G
    return None
