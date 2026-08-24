from open_omada_device_agent.contexts.clients.domain import WirelessClientState
from open_omada_device_agent.projections.inform import InformAssembler, LanObservation


def test_inform_assembler_separates_observation_from_wire_projection():
    assembler = InformAssembler(
        device_info=lambda: {"name": "ap", "isFactory": True},
        lan=LanObservation(rate=100.0, duplex=1, port="LAN"),
        clients=lambda: (WirelessClientState(mac="aa:bb:cc:dd:ee:ff"),),
        client_projection=lambda clients: [{"mac": clients[0].mac}],
        wireless_projection=lambda: {"wSettings_2G": {"ch": "6"}},
    )

    body = assembler.build(need_reply=True, uptime=12)

    assert body["deviceInfo"]["upTime"] == "12"
    assert body["deviceInfo"]["isFactory"] is False
    assert body["clients"] == [{"mac": "aa:bb:cc:dd:ee:ff"}]
    assert body["wSettings_2G"] == {"ch": "6"}
