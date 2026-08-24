"""Parse Omada AP SET_REQUEST bodies into platform-independent domain updates."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .domain import (
    AccessPointConfigUpdate,
    CaptivePortalBinding,
    DhcpOption82,
    LedConfig,
    ManagementVlan,
    PortalFreePolicy,
    RadioBand,
    RadioConfig,
    SecretValue,
    VlanAssignment,
    WifiControlLedConfig,
    WirelessNetwork,
    WirelessSecurity,
    validate_ssid_name,
    validate_vlan_id,
)

RADIO_KEYS: dict[str, RadioBand] = {
    "wirelessBasic_2G": RadioBand.TWO_G,
    "wirelessBasic_5G": RadioBand.FIVE_G,
    "wirelessBasic_5G2": RadioBand.FIVE_G2,
    "wirelessBasic_6G": RadioBand.SIX_G,
}

SSID_KEYS: dict[str, RadioBand] = {
    "ssid_2G": RadioBand.TWO_G,
    "ssid_5G": RadioBand.FIVE_G,
    "ssid_5G2": RadioBand.FIVE_G2,
    "ssid_6G": RadioBand.SIX_G,
}

KNOWN_COMMON_KEYS = {"sequenceId", "configVersion", "configVersionInc"}
KNOWN_CONFIG_KEYS = set(RADIO_KEYS) | set(SSID_KEYS) | {
    "led",
    "managementVlan",
    "portalFreePolicyConfig",
    "wifiControlLed",
}


def parse_set_request(message: Mapping[str, Any]) -> AccessPointConfigUpdate:
    body = message.get("body")
    if not isinstance(body, Mapping):
        raise ValueError("SET_REQUEST body must be a JSON object")
    return parse_config_body(body)


def parse_config_body(body: Mapping[str, Any]) -> AccessPointConfigUpdate:
    radios = []
    wlans = []

    for key, band in RADIO_KEYS.items():
        raw = body.get(key)
        if raw is not None:
            radios.append(_parse_radio_config(band, raw))

    for key, band in SSID_KEYS.items():
        raw = body.get(key)
        if raw is not None:
            wlans.extend(_parse_ssid_config(band, raw))

    management_vlan = None
    raw_management_vlan = body.get("managementVlan")
    if raw_management_vlan is not None:
        management_vlan = _parse_management_vlan(raw_management_vlan)

    portal_free_policy = None
    raw_portal_free_policy = body.get("portalFreePolicyConfig")
    if raw_portal_free_policy is not None:
        portal_free_policy = _parse_portal_free_policy(raw_portal_free_policy)

    led = None
    raw_led = body.get("led")
    if raw_led is not None:
        led = _parse_led(raw_led)

    wifi_control_led = None
    raw_wifi_control_led = body.get("wifiControlLed")
    if raw_wifi_control_led is not None:
        wifi_control_led = _parse_wifi_control_led(raw_wifi_control_led)

    unhandled = tuple(
        sorted(
            key
            for key in body
            if key not in KNOWN_COMMON_KEYS and key not in KNOWN_CONFIG_KEYS
        )
    )
    return AccessPointConfigUpdate(
        sequence_id=_optional_int(body.get("sequenceId")),
        config_version=_optional_int(body.get("configVersion")),
        config_version_inc=_optional_int(body.get("configVersionInc")),
        radios=tuple(radios),
        wlans=tuple(wlans),
        management_vlan=management_vlan,
        portal_free_policy=portal_free_policy,
        led=led,
        wifi_control_led=wifi_control_led,
        unhandled_keys=unhandled,
        raw_body=dict(body),
    )


def _parse_radio_config(band: RadioBand, raw: Any) -> RadioConfig:
    data = _require_mapping(raw, f"{band.value} radio config")
    return RadioConfig(
        band=band,
        radio_id=_optional_int(data.get("radioId")),
        enabled=_optional_bool(data.get("radioEnable")),
        channel_width=_optional_int(data.get("chanWidth")),
        channel=_optional_int(data.get("channel")),
        tx_power=_optional_int(data.get("txPower")),
        channel_limit=_optional_bool(data.get("channelLimit")),
        wireless_mode=_optional_int(data.get("wirelessMode")),
        raw=dict(data),
    )


def _parse_ssid_config(band: RadioBand, raw: Any) -> tuple[WirelessNetwork, ...]:
    data = _require_mapping(raw, f"{band.value} SSID config")
    radio_id = _optional_int(data.get("radioId"))
    ssid_items = data.get("ssid", ())
    return tuple(
        _parse_ssid_item(band, radio_id, item)
        for item in _iter_ssid_items(ssid_items)
    )


def _parse_ssid_item(
    band: RadioBand,
    radio_id: int | None,
    raw: Any,
) -> WirelessNetwork:
    data = _require_mapping(raw, f"{band.value} SSID item")
    name = validate_ssid_name(str(data.get("ssidName") or ""))
    vlan_id = _optional_int(data.get("vlanId"))
    if vlan_id is not None:
        validate_vlan_id(vlan_id)
    fast_transition = data.get("fastTransition")
    return WirelessNetwork(
        band=band,
        radio_id=radio_id,
        ssid_id=_optional_int(data.get("id")),
        index=_optional_int(data.get("index")),
        operation=_optional_int(data.get("operation")),
        name=name,
        broadcast=_optional_bool(data.get("ssidBcast")),
        client_isolation=_optional_bool(data.get("ssidIsolation")),
        vlan=VlanAssignment(
            vlan_id=vlan_id,
            vlan_pool_ids=tuple(str(value) for value in data.get("vlanPoolIds") or ()),
            dynamic_vlan_mode=_optional_int(data.get("dyVlanMode")),
            dhcp_option82=_parse_dhcp_option82(data.get("dhcpOp82")),
        ),
        security=WirelessSecurity(
            security_mode=_optional_int(data.get("securityMode")),
            auth_type=_optional_int(data.get("authType")),
            wpa_version=_optional_int(data.get("wpaVer")),
            wpa_cipher=_optional_int(data.get("wpaCipher")),
            psk_version=_optional_int(data.get("pskVer")),
            psk_cipher=_optional_int(data.get("pskCipher")),
            psk_configured=bool(data.get("pskKey")),
            psk_key=(
                SecretValue(str(data["pskKey"]))
                if data.get("pskKey") is not None
                else None
            ),
            radius_profile_id=_optional_str(data.get("wpaRadiusProfileId")),
            radius_auth=_optional_mapping(data.get("radiusAuth")),
            radius_accounting=_optional_mapping(data.get("radiusAccounting")),
            radius_mac_auth=_optional_mapping(data.get("macAuth")),
            pmf_mode=_optional_int(data.get("pmfMode")),
            fast_roaming=(
                _optional_bool(fast_transition.get("enable11r"))
                if isinstance(fast_transition, Mapping)
                else None
            ),
            raw=dict(data),
        ),
        portal=CaptivePortalBinding(
            enabled=bool(data.get("portal")),
            https_redirect=_optional_bool(data.get("httpsRedirectEnable")),
            hotspot_v2=_optional_mapping(data.get("hotspotV2")),
            raw=dict(data),
        ),
        raw=dict(data),
    )


def _parse_dhcp_option82(raw: Any) -> DhcpOption82 | None:
    if raw is None:
        return None
    data = _require_mapping(raw, "DHCP option 82 config")
    return DhcpOption82(
        enabled=bool(data.get("option82En")),
        format=_optional_int(data.get("option82Format")),
        delimiter=_optional_str(data.get("delimiter")),
        circuit_id=tuple(int(value) for value in data.get("circuitId") or ()),
        remote_id=tuple(int(value) for value in data.get("remoteId") or ()),
        site_name=_optional_str(data.get("siteName")),
        raw=dict(data),
    )


def _parse_management_vlan(raw: Any) -> ManagementVlan:
    data = _require_mapping(raw, "management VLAN config")
    enabled = _enabled_string(data.get("managementVlanEnable"))
    vlan_id = _optional_int(data.get("managementVlanId"))
    if enabled and vlan_id is not None:
        validate_vlan_id(vlan_id)
    return ManagementVlan(enabled=enabled, vlan_id=vlan_id, raw=dict(data))


def _parse_portal_free_policy(raw: Any) -> PortalFreePolicy:
    data = _require_mapping(raw, "portal free policy config")
    return PortalFreePolicy(
        layer2_rules=tuple(
            _require_mapping(item, "portal free policy item")
            for item in data.get("portalFreePolicy") or ()
        ),
        url_rules=tuple(
            _require_mapping(item, "portal URL free policy item")
            for item in data.get("urlPortalFreePolicy") or ()
        ),
        raw=dict(data),
    )


def _parse_led(raw: Any) -> LedConfig:
    data = _require_mapping(raw, "LED config")
    return LedConfig(
        enabled=_optional_enabled(data.get("enable")),
        locate=_optional_bool(data.get("locate")),
        raw=dict(data),
    )


def _parse_wifi_control_led(raw: Any) -> WifiControlLedConfig:
    data = _require_mapping(raw, "WiFi control LED config")
    return WifiControlLedConfig(
        enabled=_optional_enabled(data.get("enable")),
        is_pressed=_optional_bool(data.get("isPressed")),
        raw=dict(data),
    )


def _iter_ssid_items(raw: Any) -> Iterable[Any]:
    if raw is None:
        return ()
    if isinstance(raw, Mapping):
        return (raw,)
    if isinstance(raw, Iterable) and not isinstance(raw, (str, bytes, bytearray)):
        return raw
    raise ValueError("SSID list must be an object or array")


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _optional_mapping(value: Any) -> Mapping[str, Any] | None:
    return dict(value) if isinstance(value, Mapping) else None


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "enable", "enabled"}
    return bool(value)


def _optional_enabled(value: Any) -> bool | None:
    if value is None:
        return None
    return _enabled_string(value)


def _enabled_string(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"on", "enable", "enabled", "true", "1", "yes"}
    return bool(value)
