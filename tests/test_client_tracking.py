from open_omada_device_agent.client_tracking import (
    client_stats_payload,
    clients_from_dhcp_leases,
    merge_wireless_client_states,
    parse_dnsmasq_leases,
)
from open_omada_device_agent.domain import RadioBand, WirelessClientState


def test_parse_dnsmasq_leases_and_merge_latest_by_mac():
    leases = parse_dnsmasq_leases(
        "\n".join(
            [
                "1000 aa:bb:cc:dd:ee:ff 192.0.2.10 phone 01:aabb",
                "1200 aa-bb-cc-dd-ee-ff 192.0.2.11 phone-new *",
                "900 02:00:00:00:00:02 192.0.2.12 * *",
            ]
        )
    )

    clients = clients_from_dhcp_leases(leases)

    assert len(clients) == 2
    assert clients[0].mac == "02:00:00:00:00:02"
    assert clients[0].hostname is None
    assert clients[1].mac == "aa:bb:cc:dd:ee:ff"
    assert clients[1].ipv4 == "192.0.2.11"
    assert clients[1].hostname == "phone-new"


def test_client_stats_payload_uses_controller_field_names():
    clients = (
        WirelessClientState(
            mac="aa:bb:cc:dd:ee:ff",
            ipv4="192.0.2.10",
            hostname="phone",
            ssid="guest",
            radio=RadioBand.TWO_G,
            rssi=-62,
            rx_bytes=123,
            tx_bytes=45,
            rx_packets=4,
            tx_packets=8,
            rx_rate=6500,
            tx_rate=7200,
            association_time=12,
        ),
    )

    payload = client_stats_payload(clients)

    assert payload == [
        {
            "mac": "aa:bb:cc:dd:ee:ff",
            "ip": "192.0.2.10",
            "name": "phone",
            "ssid": "guest",
            "rid": 0,
            "rssi": -62,
            "down": 123,
            "up": 45,
            "rxP": 4,
            "txP": 8,
            "rxR": 6500,
            "txR": 7200,
            "aTime": 12,
        }
    ]


def test_merge_wireless_client_states_preserves_dhcp_identity_and_hostapd_metrics():
    dhcp_clients = clients_from_dhcp_leases(
        parse_dnsmasq_leases("1000 aa:bb:cc:dd:ee:ff 192.0.2.10 phone *")
    )
    hostapd_clients = (
        WirelessClientState(
            mac="aa:bb:cc:dd:ee:ff",
            ssid="guest",
            radio=RadioBand.TWO_G,
            rssi=-60,
            rx_bytes=100,
            tx_bytes=20,
        ),
    )

    merged = merge_wireless_client_states(dhcp_clients, hostapd_clients)

    assert merged == (
        WirelessClientState(
            mac="aa:bb:cc:dd:ee:ff",
            ipv4="192.0.2.10",
            hostname="phone",
            ssid="guest",
            radio=RadioBand.TWO_G,
            rssi=-60,
            rx_bytes=100,
            tx_bytes=20,
        ),
    )
