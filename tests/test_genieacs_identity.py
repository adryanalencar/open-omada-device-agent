from dataclasses import replace

import pytest

from open_omada_device_agent.adapters.outbound.genieacs.identity import (
    TR098_IDENTITY_PATHS,
    TR098_MAC_CANDIDATES,
    TR181_IDENTITY_PATHS,
    TR181_MAC_CANDIDATES,
    extract_identity,
    select_identity_mac,
)
from open_omada_device_agent.adapters.outbound.genieacs.models import MacCandidate
from open_omada_device_agent.adapters.outbound.genieacs.parameters import (
    GenieAcsParameterError,
    normalize_parameters,
)
from open_omada_device_agent.application.settings import GenieAcsSettings
from open_omada_device_agent.bootstrap import AgentSettings


def test_extracts_tr181_identity_from_parameters_and_top_level_device_id():
    tree = normalize_parameters(
        {
            "_id": "001122-Example-ABC123",
            "_deviceId": {
                "_Manufacturer": "MetadataManufacturer",
                "_OUI": "00-11-22",
                "_ProductClass": "MetadataProduct",
                "_SerialNumber": "MetadataSerial",
            },
            "Device": {
                "DeviceInfo": {
                    "Manufacturer": {"_value": "Example"},
                    "ProductClass": {"_value": "Router X"},
                    "SerialNumber": {"_value": "SN123"},
                    "SoftwareVersion": {"_value": "1.2.3"},
                    "HardwareVersion": {"_value": "A1"},
                },
                "Ethernet": {
                    "Interface": {
                        "1": {"MACAddress": {"_value": "aa:bb:cc:dd:ee:ff"}}
                    }
                },
            },
        }
    )

    identity = extract_identity(
        tree,
        identity_paths=TR181_IDENTITY_PATHS,
        mac_candidates=TR181_MAC_CANDIDATES,
    )

    assert identity.genieacs_id == "001122-Example-ABC123"
    assert identity.manufacturer == "Example"
    assert identity.oui == "001122"
    assert identity.product_class == "Router X"
    assert identity.serial_number == "SN123"
    assert identity.software_version == "1.2.3"
    assert identity.hardware_version == "A1"
    assert identity.mac == "aa:bb:cc:dd:ee:ff"
    assert identity.mac_source == "Device.Ethernet.Interface.1.MACAddress"


def test_extracts_tr098_identity_and_mac_from_legacy_paths():
    tree = normalize_parameters(
        {
            "_id": "legacy-device",
            "InternetGatewayDevice": {
                "DeviceInfo": {
                    "Manufacturer": {"_value": "Legacy"},
                    "ManufacturerOUI": {"_value": "AA:BB:CC"},
                    "ProductClass": {"_value": "ONT"},
                    "SerialNumber": {"_value": "ONT123"},
                },
                "LANDevice": {
                    "1": {
                        "WLANConfiguration": {
                            "1": {"BSSID": {"_value": "9E-27-26-62-6D-EC"}}
                        }
                    }
                },
            },
        }
    )

    identity = extract_identity(
        tree,
        identity_paths=TR098_IDENTITY_PATHS,
        mac_candidates=TR098_MAC_CANDIDATES,
    )

    assert identity.manufacturer == "Legacy"
    assert identity.oui == "AABBCC"
    assert identity.product_class == "ONT"
    assert identity.serial_number == "ONT123"
    assert identity.mac == "9e:27:26:62:6d:ec"


def test_select_identity_mac_prefers_configured_paths_then_profile_candidates():
    tree = normalize_parameters(
        {
            "_id": "device",
            "Device": {
                "Ethernet": {
                    "Interface": {
                        "1": {"MACAddress": {"_value": "aa:bb:cc:dd:ee:ff"}}
                    }
                },
                "WiFi": {
                    "SSID": {
                        "2": {"MACAddress": {"_value": "02-11-22-33-44-55"}}
                    }
                },
            },
        }
    )

    selected = select_identity_mac(
        tree,
        preferred_paths=("Device.WiFi.SSID.2.MACAddress",),
        mac_candidates=(MacCandidate("Device.Ethernet.Interface.1.MACAddress", "lan", 1),),
    )

    assert selected is not None
    assert selected.mac == "02:11:22:33:44:55"
    assert selected.path == "Device.WiFi.SSID.2.MACAddress"
    assert selected.role == "configured"


def test_select_identity_mac_skips_invalid_candidate_values():
    tree = normalize_parameters(
        {
            "_id": "device",
            "Device": {
                "WiFi": {
                    "SSID": {
                        "1": {"MACAddress": {"_value": "bad"}},
                        "2": {"MACAddress": {"_value": "02-11-22-33-44-55"}},
                    }
                }
            },
        }
    )

    selected = select_identity_mac(
        tree,
        mac_candidates=(
            MacCandidate("Device.WiFi.SSID.1.MACAddress", "bad", 1),
            MacCandidate("Device.WiFi.SSID.2.MACAddress", "good", 2),
        ),
    )

    assert selected is not None
    assert selected.mac == "02:11:22:33:44:55"
    assert selected.role == "good"


def test_extract_identity_requires_genieacs_id():
    tree = normalize_parameters({"Device": {"DeviceInfo": {"Manufacturer": {"_value": "x"}}}})

    with pytest.raises(GenieAcsParameterError, match="_id"):
        extract_identity(
            tree,
            identity_paths=TR181_IDENTITY_PATHS,
            mac_candidates=TR181_MAC_CANDIDATES,
        )


def test_settings_validate_genieacs_identity_mac_paths():
    settings = replace(
        AgentSettings.from_environment(),
        platform="genieacs",
        controller_host="controller.example.test",
        genieacs=GenieAcsSettings(
            url="https://acs.example.test:7557",
            device_id="device-id",
            identity_mac_paths=("Device.WiFi.SSID.1.MACAddress",),
        ),
    )

    settings.validate()


def test_settings_reject_invalid_genieacs_identity_mac_path():
    settings = replace(
        AgentSettings.from_environment(),
        platform="genieacs",
        controller_host="controller.example.test",
        genieacs=GenieAcsSettings(
            url="https://acs.example.test:7557",
            device_id="device-id",
            identity_mac_paths=("Device.WiFi..SSID",),
        ),
    )

    with pytest.raises(RuntimeError, match="GENIEACS_IDENTITY_MAC_PATHS"):
        settings.validate()
