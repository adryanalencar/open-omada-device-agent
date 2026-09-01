from datetime import datetime, timedelta, timezone

import pytest

from open_omada_device_agent.adapters.outbound.genieacs.parameters import (
    GenieAcsParameter,
    GenieAcsParameterError,
    ParameterTree,
    ParameterWrite,
    normalize_parameters,
    task_entries,
)


def test_normalizes_nested_and_flat_genieacs_parameter_shapes():
    tree = normalize_parameters(
        {
            "_id": "001122-Example-ABC123",
            "_lastInform": "2026-08-31T10:00:00.000Z",
            "Device": {
                "DeviceInfo": {
                    "Manufacturer": {
                        "_value": "Example",
                        "_type": "xsd:string",
                        "_writable": False,
                        "_timestamp": "2026-08-31T09:59:30.000Z",
                    }
                },
                "WiFi": {
                    "Radio": {
                        "1": {
                            "Enable": {
                                "_value": True,
                                "_type": "xsd:boolean",
                                "_writable": True,
                                "_timestamp": "2026-08-31T09:59:31+00:00",
                            },
                            "Channel": {
                                "_value": "6",
                                "_type": "xsd:unsignedInt",
                                "_writable": "true",
                            },
                        }
                    }
                },
            },
            "Device.WiFi.AccessPoint.1.AssociatedDevice.1.MACAddress": {
                "_value": "9E-27-26-62-6D-EC",
                "_type": "xsd:string",
                "_writable": False,
            },
        }
    )

    assert tree.device_id == "001122-Example-ABC123"
    assert tree.last_inform == datetime(2026, 8, 31, 10, 0, tzinfo=timezone.utc)
    assert tree.root_exists("Device") is True
    assert tree.root_exists("InternetGatewayDevice") is False
    assert tree.get_or_missing("Device.DeviceInfo.Manufacturer").as_string() == "Example"
    assert tree.get_or_missing("Device.WiFi.Radio.1.Enable").as_bool() is True
    assert tree.get_or_missing("Device.WiFi.Radio.1.Enable").writable is True
    assert tree.get_or_missing("Device.WiFi.Radio.1.Channel").as_uint() == 6
    assert (
        tree.get_or_missing("Device.WiFi.AccessPoint.1.AssociatedDevice.1.MACAddress").as_mac()
        == "9e:27:26:62:6d:ec"
    )


def test_detects_tr098_root_without_assuming_wlan_instance_meaning():
    tree = normalize_parameters(
        {
            "_id": "legacy-cpe",
            "InternetGatewayDevice": {
                "LANDevice": {
                    "1": {
                        "WLANConfiguration": {
                            "3": {
                                "SSID": {
                                    "_value": "Legacy WiFi",
                                    "_type": "xsd:string",
                                    "_writable": True,
                                }
                            }
                        }
                    }
                }
            },
        }
    )

    assert tree.root_exists("InternetGatewayDevice") is True
    assert tree.get_or_missing(
        "InternetGatewayDevice.LANDevice.1.WLANConfiguration.3.SSID"
    ).as_string() == "Legacy WiFi"


def test_parameter_coercion_handles_missing_defaults_and_rejects_bad_values():
    missing = GenieAcsParameter.missing("Device.WiFi.Radio.1.Enable")
    assert missing.as_bool(default=False) is False
    assert missing.as_string(default="unknown") == "unknown"

    assert GenieAcsParameter("x", "enabled").as_bool() is True
    assert GenieAcsParameter("x", "0").as_bool() is False
    assert GenieAcsParameter("x", "0x10").as_int() == 16
    assert GenieAcsParameter("x", 42).as_uint() == 42

    with pytest.raises(GenieAcsParameterError, match="boolean"):
        GenieAcsParameter("x", "maybe").as_bool()
    with pytest.raises(GenieAcsParameterError, match="unsigned"):
        GenieAcsParameter("x", -1).as_uint()
    with pytest.raises(GenieAcsParameterError, match="MAC"):
        GenieAcsParameter("x", "not-a-mac").as_mac()


def test_parameter_freshness_uses_parameter_timestamp_conservatively():
    now = datetime(2026, 8, 31, 10, 0, tzinfo=timezone.utc)
    fresh = GenieAcsParameter(
        "Device.WiFi.Radio.1.Channel",
        6,
        timestamp=now - timedelta(seconds=30),
    )
    stale = GenieAcsParameter(
        "Device.WiFi.Radio.1.Channel",
        6,
        timestamp=now - timedelta(seconds=301),
    )
    unknown = GenieAcsParameter("Device.WiFi.Radio.1.Channel", 6)

    assert fresh.is_stale(max_age_seconds=300, now=now) is False
    assert stale.is_stale(max_age_seconds=300, now=now) is True
    assert unknown.is_stale(max_age_seconds=300, now=now) is True


def test_tree_prefix_queries_are_sorted_and_immutable():
    tree = ParameterTree.from_genieacs_device(
        {
            "Device": {
                "WiFi": {
                    "SSID": {
                        "2": {"SSID": {"_value": "B"}},
                        "1": {"SSID": {"_value": "A"}},
                    }
                }
            }
        }
    )

    names = tuple(parameter.as_string() for parameter in tree.with_prefix("Device.WiFi.SSID"))

    assert names == ("A", "B")
    with pytest.raises(TypeError):
        tree.parameters["Device.WiFi.SSID.3.SSID"] = GenieAcsParameter("x", "C")


def test_parameter_write_preserves_xsd_types_for_set_parameter_values():
    writes = (
        ParameterWrite.infer("Device.WiFi.Radio.1.Enable", True),
        ParameterWrite.infer("Device.WiFi.Radio.1.Channel", 6),
        ParameterWrite("Device.WiFi.SSID.1.SSID", "Media Beach", "xsd:string"),
    )

    assert task_entries(writes) == [
        ["Device.WiFi.Radio.1.Enable", True, "xsd:boolean"],
        ["Device.WiFi.Radio.1.Channel", 6, "xsd:unsignedInt"],
        ["Device.WiFi.SSID.1.SSID", "Media Beach", "xsd:string"],
    ]


def test_rejects_invalid_parameter_write_path():
    with pytest.raises(GenieAcsParameterError, match="invalid TR-069"):
        ParameterWrite.infer("Device.WiFi..SSID", "bad")
