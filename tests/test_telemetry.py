import json
from dataclasses import dataclass

import open_omada_device_agent.adoption as adoption
from open_omada_device_agent.openwrt import CommandResult
from open_omada_device_agent.platform_capabilities import PlatformCapabilities
from open_omada_device_agent.telemetry import (
    OpenWrtWirelessTelemetry,
    collect_openwrt_wireless_inform,
    openwrt_wireless_inform_from_status,
)


@dataclass
class StaticRunner:
    result: CommandResult
    calls: list[tuple[str, ...]]

    def run(self, args, *, input_text=None):
        assert input_text is None
        self.calls.append(tuple(args))
        return self.result


def test_maps_openwrt_wireless_status_to_omada_inform_keys():
    status = {
        "radio0": {
            "config": {
                "channel": "11",
                "htmode": "HT20",
                "hwmode": "11g",
                "txpower": 17,
            },
            "interfaces": [
                {
                    "config": {"ssid": "guest"},
                    "bssid": "02:00:00:00:00:10",
                    "stations": {"aa:bb:cc:dd:ee:ff": {}},
                    "statistics": {
                        "tx_bytes": "1234",
                        "rx_bytes": "567",
                        "tx_packets": 12,
                        "rx_packets": 7,
                    },
                }
            ],
        },
        "radio1": {
            "config": {"channel": 36, "htmode": "VHT80"},
            "interfaces": [{"config": {"ssid": "corp"}, "num_sta": 2}],
        },
    }

    payload = openwrt_wireless_inform_from_status(status)

    assert payload["wSettings_2G"] == {
        "ch": "11",
        "bw": "HT20",
        "rdMode": "11g",
        "txPower": "17",
        "staNum": 1,
    }
    assert payload["ssidStats_2G"] == [
        {
            "ssid": "guest",
            "clntNum": 1,
            "bssid": "02:00:00:00:00:10",
            "down": 1234,
            "up": 567,
            "downPkts": 12,
            "upPkts": 7,
        }
    ]
    assert payload["wSettings_5G"] == {"ch": "36", "bw": "VHT80", "staNum": 2}
    assert payload["ssidStats_5G"] == [{"ssid": "corp", "clntNum": 2}]


def test_collect_openwrt_wireless_telemetry_uses_ubus_without_shell():
    runner = StaticRunner(
        result=CommandResult(
            returncode=0,
            stdout=json.dumps({"radio0": {"config": {"channel": 6}, "interfaces": []}}),
        ),
        calls=[],
    )
    caps = PlatformCapabilities(platform="openwrt", has_ubus=True)

    payload = collect_openwrt_wireless_inform(capabilities=caps, runner=runner)

    assert payload == {"wSettings_2G": {"ch": "6"}}
    assert runner.calls == [("ubus", "call", "network.wireless", "status")]


def test_collect_openwrt_wireless_telemetry_is_empty_without_ubus():
    runner = StaticRunner(result=CommandResult(returncode=0, stdout="{}"), calls=[])
    caps = PlatformCapabilities(platform="openwrt", has_ubus=False)

    assert collect_openwrt_wireless_inform(capabilities=caps, runner=runner) == {}
    assert runner.calls == []


def test_openwrt_wireless_telemetry_ignores_invalid_json():
    runner = StaticRunner(result=CommandResult(returncode=0, stdout="{not-json"), calls=[])

    assert OpenWrtWirelessTelemetry(runner).collect() == {}


def test_inform_body_includes_wireless_telemetry_when_available(monkeypatch):
    monkeypatch.setattr(
        adoption,
        "collect_openwrt_wireless_inform",
        lambda: {"wSettings_2G": {"ch": "11"}},
    )

    body = adoption._inform_body(need_reply=False, started_at=0)

    assert body["wSettings_2G"] == {"ch": "11"}
