import json
from dataclasses import dataclass

from open_omada_device_agent.domain import RadioBand, WirelessClientState
from open_omada_device_agent.contexts.clients.domain import ClientRadioBand
from open_omada_device_agent.openwrt import CommandResult
from open_omada_device_agent.platform_capabilities import PlatformCapabilities
from open_omada_device_agent.telemetry import (
    OpenWrtWirelessInterface,
    OpenWrtWirelessTelemetry,
    collect_openwrt_wireless_clients,
    collect_openwrt_wireless_inform,
    hostapd_client_states,
    openwrt_wireless_interfaces_from_status,
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


@dataclass
class SequenceRunner:
    results: list[CommandResult]
    calls: list[tuple[str, ...]]

    def run(self, args, *, input_text=None):
        assert input_text is None
        self.calls.append(tuple(args))
        return self.results.pop(0)


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


def test_collect_openwrt_wireless_telemetry_uses_hostapd_for_ssid_client_counts():
    runner = SequenceRunner(
        results=[
            CommandResult(
                returncode=0,
                stdout=json.dumps(
                    {
                        "radio0": {
                            "config": {"channel": 6, "htmode": "HT20"},
                            "interfaces": [
                                {
                                    "ifname": "phy0-ap0",
                                    "config": {"ssid": "guest"},
                                    "stations": [],
                                }
                            ],
                        }
                    }
                ),
            ),
            CommandResult(
                returncode=0,
                stdout=json.dumps(
                    {
                        "clients": {
                            "aa:bb:cc:dd:ee:ff": {
                                "bytes": {"rx": 100, "tx": 200},
                                "packets": {"rx": 1, "tx": 2},
                            }
                        }
                    }
                ),
            ),
        ],
        calls=[],
    )
    caps = PlatformCapabilities(platform="openwrt", has_ubus=True)

    payload = collect_openwrt_wireless_inform(capabilities=caps, runner=runner)

    assert payload["wSettings_2G"] == {"ch": "6", "bw": "HT20", "staNum": 1}
    assert payload["ssidStats_2G"] == [
        {
            "ssid": "guest",
            "clntNum": 1,
            "down": 200,
            "up": 100,
            "downPkts": 2,
            "upPkts": 1,
        }
    ]
    assert runner.calls == [
        ("ubus", "call", "network.wireless", "status"),
        ("ubus", "call", "hostapd.phy0-ap0", "get_clients"),
    ]


def test_collect_openwrt_wireless_telemetry_is_empty_without_ubus():
    runner = StaticRunner(result=CommandResult(returncode=0, stdout="{}"), calls=[])
    caps = PlatformCapabilities(platform="openwrt", has_ubus=False)

    assert collect_openwrt_wireless_inform(capabilities=caps, runner=runner) == {}
    assert runner.calls == []


def test_extracts_hostapd_interfaces_from_openwrt_wireless_status():
    interfaces = openwrt_wireless_interfaces_from_status(
        {
            "radio0": {
                "interfaces": [
                    {"ifname": "wlan0", "config": {"ssid": "guest"}},
                    {"section": "wlan0-1", "config": {"ssid": "iot"}},
                ]
            }
        }
    )

    assert interfaces == (
        OpenWrtWirelessInterface(ifname="wlan0", ssid="guest", band=RadioBand.TWO_G),
        OpenWrtWirelessInterface(ifname="wlan0-1", ssid="iot", band=RadioBand.TWO_G),
    )


def test_maps_hostapd_clients_to_wireless_client_state():
    clients = hostapd_client_states(
        OpenWrtWirelessInterface(ifname="wlan0", ssid="guest", band=RadioBand.TWO_G),
        {
            "clients": {
                "AA-BB-CC-DD-EE-FF": {
                    "signal": -61,
                    "snr": 35,
                    "bytes": {"tx": 1200, "rx": 345},
                    "packets": {"tx": 12, "rx": 5},
                    "rate": {"tx": 7200, "rx": 6500},
                    "connected_time": 42,
                }
            }
        },
    )

    assert len(clients) == 1
    assert clients[0].mac == "aa:bb:cc:dd:ee:ff"
    assert clients[0].ssid == "guest"
    assert clients[0].radio is ClientRadioBand.TWO_G
    assert clients[0].rssi == -61
    assert clients[0].snr == 35
    assert clients[0].rx_bytes == 1200
    assert clients[0].tx_bytes == 345
    assert clients[0].tx_packets == 12
    assert clients[0].rx_packets == 5
    assert clients[0].tx_rate == 7200
    assert clients[0].rx_rate == 6500
    assert clients[0].association_time == 42


def test_collect_openwrt_wireless_clients_discovers_and_queries_hostapd():
    runner = SequenceRunner(
        results=[
            CommandResult(
                returncode=0,
                stdout=json.dumps(
                    {"radio0": {"interfaces": [{"ifname": "wlan0", "config": {"ssid": "guest"}}]}}
                ),
            ),
            CommandResult(
                returncode=0,
                stdout=json.dumps({"clients": {"aa:bb:cc:dd:ee:ff": {"signal": -60}}}),
            ),
        ],
        calls=[],
    )
    caps = PlatformCapabilities(platform="openwrt", has_ubus=True)

    clients = collect_openwrt_wireless_clients(capabilities=caps, runner=runner)

    assert [client.mac for client in clients] == ["aa:bb:cc:dd:ee:ff"]
    assert runner.calls == [
        ("ubus", "call", "network.wireless", "status"),
        ("ubus", "call", "hostapd.wlan0", "get_clients"),
    ]


def test_openwrt_wireless_telemetry_ignores_invalid_json():
    runner = StaticRunner(result=CommandResult(returncode=0, stdout="{not-json"), calls=[])

    assert OpenWrtWirelessTelemetry(runner).collect() == {}


def test_inform_projection_includes_wireless_telemetry():
    from open_omada_device_agent.projections.inform import InformAssembler, LanObservation
    assembler = InformAssembler(
        device_info=lambda: {"model": "test"},
        lan=LanObservation(100.0, 1, "LAN"),
        clients=lambda: (),
        client_projection=lambda clients: [],
        wireless_projection=lambda: {"wSettings_2G": {"ch": "11"}},
    )
    body = assembler.build(need_reply=False, uptime=0)
    assert body["wSettings_2G"] == {"ch": "11"}


def test_inform_projection_accepts_merged_dhcp_and_hostapd_clients(tmp_path):
    from open_omada_device_agent.client_tracking import client_stats_payload, clients_from_dhcp_leases, load_dnsmasq_leases, merge_wireless_client_states
    from open_omada_device_agent.projections.inform import InformAssembler, LanObservation
    lease_file = tmp_path / "leases"
    lease_file.write_text("1000 aa:bb:cc:dd:ee:ff 192.0.2.10 phone *\n", encoding="utf-8")
    clients = merge_wireless_client_states(
        clients_from_dhcp_leases(load_dnsmasq_leases(str(lease_file))),
        (WirelessClientState(mac="aa:bb:cc:dd:ee:ff", ssid="guest", radio=ClientRadioBand.TWO_G, rssi=-59),),
    )
    assembler = InformAssembler(
        device_info=lambda: {"model": "test"},
        lan=LanObservation(100.0, 1, "LAN"),
        clients=lambda: clients,
        client_projection=client_stats_payload,
        wireless_projection=lambda: {},
    )
    body = assembler.build(need_reply=False, uptime=0)
    client = body["clients"][0]
    assert client["mac"] == "aa:bb:cc:dd:ee:ff"
    assert client["ip"] == "192.0.2.10"
    assert client["name"] == "phone"
    assert client["ssid"] == "guest"
    assert client["rid"] == 0
    assert client["rssi"] == -59
