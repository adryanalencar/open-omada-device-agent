"""Device identity extraction for GenieACS-backed CPEs."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from ....shared.domain import MacAddress
from .models import GenieAcsDeviceIdentity, MacCandidate, MacSelection
from .parameters import GenieAcsParameterError, ParameterTree


TR181_IDENTITY_PATHS = {
    "manufacturer": "Device.DeviceInfo.Manufacturer",
    "oui": "Device.DeviceInfo.ManufacturerOUI",
    "product_class": "Device.DeviceInfo.ProductClass",
    "serial_number": "Device.DeviceInfo.SerialNumber",
    "software_version": "Device.DeviceInfo.SoftwareVersion",
    "hardware_version": "Device.DeviceInfo.HardwareVersion",
}

TR098_IDENTITY_PATHS = {
    "manufacturer": "InternetGatewayDevice.DeviceInfo.Manufacturer",
    "oui": "InternetGatewayDevice.DeviceInfo.ManufacturerOUI",
    "product_class": "InternetGatewayDevice.DeviceInfo.ProductClass",
    "serial_number": "InternetGatewayDevice.DeviceInfo.SerialNumber",
    "software_version": "InternetGatewayDevice.DeviceInfo.SoftwareVersion",
    "hardware_version": "InternetGatewayDevice.DeviceInfo.HardwareVersion",
}

TR181_MAC_CANDIDATES = (
    MacCandidate("Device.Ethernet.Interface.1.MACAddress", "lan", 10),
    MacCandidate("Device.WiFi.SSID.1.MACAddress", "wifi-ssid", 20),
    MacCandidate("Device.WiFi.Radio.1.MACAddress", "wifi-radio", 30),
    MacCandidate("Device.IP.Interface.1.MACAddress", "ip-interface", 40),
)

TR098_MAC_CANDIDATES = (
    MacCandidate("InternetGatewayDevice.LANDevice.1.LANEthernetInterfaceConfig.1.MACAddress", "lan", 10),
    MacCandidate("InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.BSSID", "wifi-bssid", 20),
    MacCandidate("InternetGatewayDevice.WANDevice.1.WANConnectionDevice.1.WANIPConnection.1.MACAddress", "wan", 30),
)


def extract_identity(
    tree: ParameterTree,
    *,
    identity_paths: Mapping[str, str],
    mac_candidates: Iterable[MacCandidate],
    preferred_mac_paths: Iterable[str] = (),
) -> GenieAcsDeviceIdentity:
    genieacs_id = tree.device_id
    if not genieacs_id:
        raise GenieAcsParameterError("GenieACS device document is missing _id")
    device_id = _top_level_device_id(tree.metadata.get("_deviceId"))
    selected_mac = select_identity_mac(
        tree,
        mac_candidates=mac_candidates,
        preferred_paths=preferred_mac_paths,
    )
    values = {
        name: _value_from_parameter_or_device_id(tree, path, device_id, name)
        for name, path in identity_paths.items()
    }
    return GenieAcsDeviceIdentity(
        genieacs_id=genieacs_id,
        manufacturer=values.get("manufacturer"),
        oui=_normalize_oui(values.get("oui")),
        product_class=values.get("product_class"),
        serial_number=values.get("serial_number"),
        software_version=values.get("software_version"),
        hardware_version=values.get("hardware_version"),
        mac=selected_mac.mac if selected_mac else None,
        mac_source=selected_mac.path if selected_mac else None,
    )


def select_identity_mac(
    tree: ParameterTree,
    *,
    mac_candidates: Iterable[MacCandidate],
    preferred_paths: Iterable[str] = (),
) -> MacSelection | None:
    candidates: list[MacCandidate] = [
        MacCandidate(path=path, role="configured", priority=index)
        for index, path in enumerate(preferred_paths)
    ]
    candidates.extend(sorted(mac_candidates, key=lambda item: (item.priority, item.path)))
    seen: set[str] = set()
    for candidate in candidates:
        if candidate.path in seen:
            continue
        seen.add(candidate.path)
        parameter = tree.get(candidate.path)
        if parameter is None or parameter.value in (None, ""):
            continue
        try:
            mac = MacAddress(str(parameter.value)).value
        except ValueError:
            continue
        return MacSelection(mac=mac, path=candidate.path, role=candidate.role)
    return None


def _value_from_parameter_or_device_id(
    tree: ParameterTree,
    path: str,
    device_id: Mapping[str, Any],
    name: str,
) -> str | None:
    parameter_value = tree.get_or_missing(path).as_string()
    if parameter_value not in (None, ""):
        return parameter_value.strip()
    metadata_value = device_id.get(_device_id_key(name))
    if metadata_value in (None, ""):
        return None
    return str(metadata_value).strip()


def _top_level_device_id(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _device_id_key(name: str) -> str:
    return {
        "manufacturer": "_Manufacturer",
        "oui": "_OUI",
        "product_class": "_ProductClass",
        "serial_number": "_SerialNumber",
    }.get(name, name)


def _normalize_oui(value: str | None) -> str | None:
    if value in (None, ""):
        return None
    compact = "".join(char for char in value if char.isalnum()).upper()
    if len(compact) != 6:
        return value.strip()
    return compact
