"""Parse Omada AP SET_REQUEST bodies into platform-independent domain updates."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .....application.commands import ApplyDeviceConfigurationCommand
from .....contexts.clients.domain import (
    ClientAuthConfig, ClientControlOperation, ClientRateConfig, ClientRateLimit,
)
from .....contexts.device.domain import LedConfig, WifiControlLedConfig
from .....contexts.networking.domain import ManagementVlan, validate_vlan_id
from .....contexts.portal.domain import PortalConfiguration, PortalFreePolicy
from .....contexts.wireless.domain import (
    CaptivePortalIntent, RadioBand, RadioConfig, WirelessDhcpOption82Intent,
    WirelessNetwork, WirelessSecurity, WirelessVlanIntent, validate_ssid_name,
)
from .....shared.domain import SecretValue

AccessPointConfigUpdate = ApplyDeviceConfigurationCommand

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
ACK_ONLY_CONFIG_KEYS = {
    "ipGroup",
    "ipv6Group",
    "lanSetting",
    "lldp",
    "logSetting",
    "macFilterGlobal",
    "schedulerGlobal",
    "snmp",
    "ssh",
}

# These AP config domains are accepted as known but currently have no local
# OpenWrt side effect. They should not block the actionable SSID/radio domains
# carried by the same SET_REQUEST.
PASSIVE_CONFIG_KEYS = {
    "schedulerAssoc",
    "wirelessAdv_2G",
    "wirelessAdv_5G",
    "wirelessAdv_5G2",
    "wirelessAdv_6G",
}

KNOWN_CONFIG_KEYS = set(RADIO_KEYS) | set(SSID_KEYS) | ACK_ONLY_CONFIG_KEYS | PASSIVE_CONFIG_KEYS | {
    "clientConfig",
    "clientOperation",
    "clientOperation_cmd",
    "clientRateConfig",
    "led",
    "managementVlan",
    "portalConfigList",
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

    portal_configs: tuple[PortalConfiguration, ...] = ()
    raw_portal_configs = body.get("portalConfigList")
    if raw_portal_configs is not None:
        portal_configs = _parse_portal_configs(raw_portal_configs)

    led = None
    raw_led = body.get("led")
    if raw_led is not None:
        led = _parse_led(raw_led)

    wifi_control_led = None
    raw_wifi_control_led = body.get("wifiControlLed")
    if raw_wifi_control_led is not None:
        wifi_control_led = _parse_wifi_control_led(raw_wifi_control_led)

    client_configs: tuple[ClientAuthConfig, ...] = ()
    raw_client_config = body.get("clientConfig")
    if raw_client_config is not None:
        client_configs = _parse_client_config(raw_client_config)

    client_operations: list[ClientControlOperation] = []
    for source_key in ("clientOperation", "clientOperation_cmd"):
        raw_client_operation = body.get(source_key)
        if raw_client_operation is not None:
            client_operations.extend(
                _parse_client_operations(raw_client_operation, source_key=source_key)
            )

    client_rate_config = None
    raw_client_rate_config = body.get("clientRateConfig")
    if raw_client_rate_config is not None:
        client_rate_config = _parse_client_rate_config(raw_client_rate_config)

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
        portal_configs=portal_configs,
        led=led,
        wifi_control_led=wifi_control_led,
        client_configs=client_configs,
        client_operations=tuple(client_operations),
        client_rate_config=client_rate_config,
        passive_keys=tuple(sorted(key for key in body if key in PASSIVE_CONFIG_KEYS)),
        ack_only_keys=tuple(sorted(key for key in body if key in ACK_ONLY_CONFIG_KEYS)),
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
    vlan_id = _optional_vlan_id(data.get("vlanId"))
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
        vlan=WirelessVlanIntent(
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
            radius_auth=_optional_active_mapping(data.get("radiusAuth")),
            radius_accounting=_optional_active_mapping(data.get("radiusAccounting")),
            radius_mac_auth=_optional_active_mapping(data.get("macAuth")),
            pmf_mode=_optional_int(data.get("pmfMode")),
            fast_roaming=(
                _optional_bool(fast_transition.get("enable11r"))
                if isinstance(fast_transition, Mapping)
                else None
            ),
            raw=dict(data),
        ),
        portal=CaptivePortalIntent(
            enabled=bool(data.get("portal")),
            https_redirect=_optional_bool(data.get("httpsRedirectEnable")),
            hotspot_v2=_optional_mapping(data.get("hotspotV2")),
            raw=dict(data),
        ),
        raw=dict(data),
    )


def _parse_dhcp_option82(raw: Any) -> WirelessDhcpOption82Intent | None:
    if raw is None:
        return None
    data = _require_mapping(raw, "DHCP option 82 config")
    return WirelessDhcpOption82Intent(
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
    vlan_id = _optional_vlan_id(data.get("managementVlanId"))
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


def _parse_portal_configs(raw: Any) -> tuple[PortalConfiguration, ...]:
    return tuple(
        _parse_portal_config_item(item)
        for item in _iter_items(raw, "portalConfigList")
    )


def _parse_portal_config_item(raw: Any) -> PortalConfiguration:
    data = _require_mapping(raw, "portalConfigList item")
    return PortalConfiguration(
        auth_type=_optional_int(data.get("authType")),
        auth_timeout=_optional_int(data.get("authTimeout")),
        portal_day=_optional_int(data.get("portalDay")),
        portal_hour=_optional_int(data.get("portalHour")),
        portal_min=_optional_int(data.get("portalMin")),
        https_redirect_enable=_optional_bool(data.get("httpsRedirectEnable")),
        redirect=_optional_bool(data.get("redirect")),
        redirect_url=_optional_str(data.get("redirectUrl")),
        auth_server_type=_optional_int(data.get("authServerType")),
        ext_auth_server=_optional_str(data.get("extAuthServer")),
        external_portal_server=_optional_str(data.get("externalPortalServer")),
        site_name=_optional_str(data.get("siteName") or data.get("site")),
        portal_title=_optional_str(data.get("portalTitle")),
        portal_accept=_optional_bool(data.get("portalAccept")),
        ssid_list=tuple(str(value) for value in data.get("ssidList") or ()),
        raw=_redact_portal_config(data),
    )


def _redact_portal_config(data: Mapping[str, Any]) -> dict[str, Any]:
    redacted = dict(data)
    for key in ("password", "radiusPassword"):
        if key in redacted:
            redacted[key] = "***"
    return redacted


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


def _parse_client_config(raw: Any) -> tuple[ClientAuthConfig, ...]:
    return tuple(_parse_client_config_item(item) for item in _iter_items(raw, "clientConfig"))


def _parse_client_config_item(raw: Any) -> ClientAuthConfig:
    data = _require_mapping(raw, "clientConfig item")
    return ClientAuthConfig(
        client_mac=_required_str(data.get("clientMac"), "clientConfig.clientMac"),
        unauthenticated=_optional_bool(data.get("unauth")),
        raw=dict(data),
    )


def _parse_client_operations(
    raw: Any,
    *,
    source_key: str,
) -> tuple[ClientControlOperation, ...]:
    return tuple(
        _parse_client_operation_item(item, source_key=source_key)
        for item in _iter_items(raw, source_key)
    )


def _parse_client_operation_item(
    raw: Any,
    *,
    source_key: str,
) -> ClientControlOperation:
    data = _require_mapping(raw, f"{source_key} item")
    return ClientControlOperation(
        client_mac=_required_str(data.get("clientMac"), f"{source_key}.clientMac"),
        operation=_optional_int(data.get("operation")),
        ssid=_optional_str(data.get("ssid")),
        radio_id=_optional_int(data.get("radioId")),
        vid=_optional_int(data.get("vid")),
        port=_optional_int(data.get("port")),
        wireless=_optional_bool(data.get("wireless")),
        source_key=source_key,
        raw=dict(data),
    )


def _parse_client_rate_config(raw: Any) -> ClientRateConfig:
    data = _require_mapping(raw, "clientRateConfig")
    limits = tuple(
        _parse_client_rate_limit(item)
        for item in _iter_items(data.get("clientRateLimit") or (), "clientRateLimit")
    )
    return ClientRateConfig(
        action=_optional_int(data.get("action")),
        limits=limits,
        raw=dict(data),
    )


def _parse_client_rate_limit(raw: Any) -> ClientRateLimit:
    data = _require_mapping(raw, "clientRateLimit item")
    return ClientRateLimit(
        mac=_required_str(data.get("mac"), "clientRateLimit.mac"),
        down=_optional_int(data.get("down")),
        up=_optional_int(data.get("up")),
        raw=dict(data),
    )


def _iter_ssid_items(raw: Any) -> Iterable[Any]:
    return _iter_items(raw, "SSID list")


def _iter_items(raw: Any, label: str) -> Iterable[Any]:
    if raw is None:
        return ()
    if isinstance(raw, Mapping):
        return (raw,)
    if isinstance(raw, Iterable) and not isinstance(raw, (str, bytes, bytearray)):
        return raw
    raise ValueError(f"{label} must be an object or array")


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _optional_mapping(value: Any) -> Mapping[str, Any] | None:
    return dict(value) if isinstance(value, Mapping) else None


def _optional_active_mapping(value: Any) -> Mapping[str, Any] | None:
    data = _optional_mapping(value)
    if not data:
        return None
    for key in ("enable", "enabled", "radiusEnable", "authEnable", "accountingEnable"):
        if key in data and not _optional_bool(data.get(key)):
            return None
    return data


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _optional_vlan_id(value: Any) -> int | None:
    vlan_id = _optional_int(value)
    if vlan_id in {None, 0}:
        return None
    return validate_vlan_id(vlan_id)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _required_str(value: Any, label: str) -> str:
    if value is None or str(value).strip() == "":
        raise ValueError(f"{label} is required")
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
