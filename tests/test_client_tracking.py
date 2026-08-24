from open_omada_device_agent.client_tracking import (
    client_stats_payload,
    clients_from_dhcp_leases,
    parse_dnsmasq_leases,
)


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
    clients = clients_from_dhcp_leases(
        parse_dnsmasq_leases("1000 aa:bb:cc:dd:ee:ff 192.0.2.10 phone *")
    )

    payload = client_stats_payload(clients)

    assert payload == [
        {
            "mac": "aa:bb:cc:dd:ee:ff",
            "ip": "192.0.2.10",
            "deviceName": "phone",
            "down": 0,
            "up": 0,
        }
    ]
