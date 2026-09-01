from dataclasses import dataclass, field
from typing import Any

import pytest

from open_omada_device_agent.adapters.outbound.genieacs.discovery import (
    DISCOVERY_PROJECTION,
    GenieAcsDeviceDiscovery,
    GenieAcsDeviceNotFound,
    GenieAcsProbeQueued,
    GenieAcsUnsupportedDevice,
)
from open_omada_device_agent.adapters.outbound.genieacs.models import (
    GenieAcsTaskResult,
    GenieAcsTaskState,
    Tr069DataModel,
)
from open_omada_device_agent.contexts.wireless.domain import RadioBand


@dataclass
class FakeGenieAcsDeviceClient:
    devices: list[dict[str, Any] | None] = field(default_factory=list)
    refresh_results: list[GenieAcsTaskResult] = field(default_factory=list)
    queries: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)
    refreshes: list[tuple[str, str, bool]] = field(default_factory=list)

    def query_device(self, device_id, *, projection=()):
        self.queries.append((device_id, tuple(projection)))
        return self.devices.pop(0)

    def refresh_object(self, device_id, object_name, *, connection_request=False):
        self.refreshes.append((device_id, object_name, connection_request))
        return self.refresh_results.pop(0)


def _executed_task():
    return GenieAcsTaskResult(GenieAcsTaskState.EXECUTED, 200, {"_id": "task"})


def _queued_task():
    return GenieAcsTaskResult(GenieAcsTaskState.QUEUED, 202, {"_id": "task"})


def _tr181_device():
    return {
        "_id": "tr181-device",
        "_deviceId": {
            "_Manufacturer": "Example",
            "_OUI": "001122",
            "_ProductClass": "Router",
            "_SerialNumber": "SN123",
        },
        "_lastInform": "2026-08-31T10:00:00.000Z",
        "Device": {
            "DeviceInfo": {
                "SoftwareVersion": {"_value": "1.2.3"},
            },
            "Ethernet": {
                "Interface": {
                    "1": {"MACAddress": {"_value": "aa:bb:cc:dd:ee:ff"}}
                }
            },
            "WiFi": {
                "Radio": {
                    "1": {
                        "OperatingFrequencyBand": {"_value": "2.4GHz"},
                        "Enable": {"_value": True, "_writable": True},
                    }
                },
                "SSID": {
                    "1": {"SSID": {"_value": "Media Beach", "_writable": True}}
                },
            },
        },
    }


def _tr098_device():
    return {
        "_id": "legacy-device",
        "InternetGatewayDevice": {
            "DeviceInfo": {
                "Manufacturer": {"_value": "Legacy"},
                "SerialNumber": {"_value": "ABC"},
            },
            "LANDevice": {
                "1": {
                    "WLANConfiguration": {
                        "1": {
                            "SSID": {"_value": "Legacy", "_writable": True},
                            "OperatingFrequencyBand": {"_value": "2.4GHz"},
                        }
                    }
                }
            },
        },
    }


def test_discovers_exact_genieacs_device_and_builds_profile_snapshot():
    client = FakeGenieAcsDeviceClient(devices=[_tr181_device()])

    snapshot = GenieAcsDeviceDiscovery(client, device_id="tr181-device").discover()

    assert client.queries == [("tr181-device", DISCOVERY_PROJECTION)]
    assert snapshot.device_id == "tr181-device"
    assert snapshot.profile_name == "tr181_generic"
    assert snapshot.data_model is Tr069DataModel.TR181
    assert snapshot.identity.genieacs_id == "tr181-device"
    assert snapshot.identity.manufacturer == "Example"
    assert snapshot.identity.mac == "aa:bb:cc:dd:ee:ff"
    assert snapshot.capabilities.radio_bands == (RadioBand.TWO_G,)
    assert snapshot.platform_capabilities.platform == "genieacs"
    assert snapshot.platform_capabilities.supports_wlan_config is True
    assert snapshot.warnings == ()


def test_discovery_uses_configured_identity_mac_paths():
    device = _tr181_device()
    device["Device"]["WiFi"]["SSID"]["2"] = {
        "SSID": {"_value": "Other"},
        "MACAddress": {"_value": "02-11-22-33-44-55"},
    }
    client = FakeGenieAcsDeviceClient(devices=[device])

    snapshot = GenieAcsDeviceDiscovery(
        client,
        device_id="tr181-device",
        preferred_mac_paths=("Device.WiFi.SSID.2.MACAddress",),
    ).discover()

    assert snapshot.identity.mac == "02:11:22:33:44:55"
    assert snapshot.identity.mac_source == "Device.WiFi.SSID.2.MACAddress"


def test_discovers_tr098_device_snapshot_after_profile_selection():
    client = FakeGenieAcsDeviceClient(devices=[_tr098_device()])

    snapshot = GenieAcsDeviceDiscovery(client, device_id="legacy-device").discover()

    assert snapshot.profile_name == "tr098_generic"
    assert snapshot.data_model is Tr069DataModel.TR098
    assert snapshot.identity.manufacturer == "Legacy"
    assert snapshot.capabilities.ssid_count == 1
    assert snapshot.platform_capabilities.radio_bands == (RadioBand.TWO_G,)


def test_discovery_reports_missing_device():
    client = FakeGenieAcsDeviceClient(devices=[None])

    with pytest.raises(GenieAcsDeviceNotFound, match="missing-device"):
        GenieAcsDeviceDiscovery(client, device_id="missing-device").discover()


def test_discovery_rejects_mismatched_genieacs_id():
    client = FakeGenieAcsDeviceClient(devices=[_tr181_device()])

    with pytest.raises(Exception, match="configured id"):
        GenieAcsDeviceDiscovery(client, device_id="other-device").discover()


def test_discovery_does_not_refresh_unsupported_tree_by_default():
    client = FakeGenieAcsDeviceClient(devices=[{"_id": "unknown", "Other": {"x": {"_value": 1}}}])

    with pytest.raises(GenieAcsUnsupportedDevice):
        GenieAcsDeviceDiscovery(client, device_id="unknown").discover()

    assert client.refreshes == []


def test_refresh_queued_for_unsupported_tree_is_not_reported_as_discovered():
    client = FakeGenieAcsDeviceClient(
        devices=[{"_id": "unknown", "Other": {"x": {"_value": 1}}}],
        refresh_results=[_queued_task(), _queued_task()],
    )

    with pytest.raises(GenieAcsProbeQueued):
        GenieAcsDeviceDiscovery(
            client,
            device_id="unknown",
            refresh_on_unsupported=True,
        ).discover()

    assert client.refreshes == [
        ("unknown", "Device.", False),
        ("unknown", "InternetGatewayDevice.", False),
    ]
    assert len(client.queries) == 1


def test_refresh_executed_for_unsupported_tree_requeries_and_discovers_profile():
    client = FakeGenieAcsDeviceClient(
        devices=[
            {"_id": "legacy-device", "Other": {"x": {"_value": 1}}},
            _tr098_device(),
        ],
        refresh_results=[_executed_task(), _executed_task()],
    )

    snapshot = GenieAcsDeviceDiscovery(
        client,
        device_id="legacy-device",
        refresh_on_unsupported=True,
    ).discover()

    assert snapshot.profile_name == "tr098_generic"
    assert len(client.queries) == 2
    assert client.refreshes == [
        ("legacy-device", "Device.", False),
        ("legacy-device", "InternetGatewayDevice.", False),
    ]


def test_snapshot_warns_when_wifi_exists_without_radio_band_information():
    device = _tr181_device()
    del device["Device"]["WiFi"]["Radio"]["1"]["OperatingFrequencyBand"]
    client = FakeGenieAcsDeviceClient(devices=[device])

    snapshot = GenieAcsDeviceDiscovery(client, device_id="tr181-device").discover()

    assert "no radio band" in snapshot.warnings[0]
