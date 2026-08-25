import pytest

from open_omada_device_agent.ap_config import parse_config_body, parse_set_request
from open_omada_device_agent.domain import (
    ClientOperationCode,
    RadioBand,
    validate_ssid_name,
    validate_vlan_id,
)


def test_parse_radio_wlan_vlan_and_portal_config_from_set_body():
    update = parse_config_body(
        {
            "sequenceId": 42,
            "configVersion": 7,
            "wirelessBasic_2G": {
                "radioId": 1,
                "radioEnable": True,
                "chanWidth": 20,
                "channel": 6,
                "txPower": 12,
                "channelLimit": False,
            },
            "ssid_2G": {
                "radioId": 1,
                "ssid": [
                    {
                        "id": 100,
                        "index": 1,
                        "operation": 1,
                        "ssidName": "lab-wlan",
                        "ssidBcast": False,
                        "ssidIsolation": True,
                        "vlanId": 30,
                        "securityMode": 3,
                        "pskVer": 2,
                        "pskCipher": 1,
                        "pskKey": "secret-value-is-not-copied-to-a-field",
                        "portal": True,
                        "httpsRedirectEnable": True,
                        "dyVlanMode": 2,
                        "dhcpOp82": {
                            "option82En": True,
                            "option82Format": 1,
                            "delimiter": ":",
                            "circuitId": [1, 2],
                            "remoteId": [3],
                            "siteName": "HQ",
                        },
                        "fastTransition": {"enable11r": True},
                    }
                ],
            },
            "managementVlan": {
                "managementVlanEnable": "on",
                "managementVlanId": 99,
            },
            "portalFreePolicyConfig": {
                "portalFreePolicy": [{"type": "ip", "value": "192.0.2.10"}],
                "urlPortalFreePolicy": [{"host": "example.com"}],
            },
            "led": {"enable": "on"},
        }
    )

    assert update.sequence_id == 42
    assert update.config_version == 7
    assert update.unhandled_keys == ()
    assert update.led is not None
    assert update.led.enabled is True
    assert update.led.locate is None

    radio = update.radios[0]
    assert radio.band is RadioBand.TWO_G
    assert radio.radio_id == 1
    assert radio.enabled is True
    assert radio.channel == 6
    assert radio.channel_width == 20
    assert radio.tx_power == 12

    wlan = update.wlans[0]
    assert wlan.band is RadioBand.TWO_G
    assert wlan.name == "lab-wlan"
    assert wlan.broadcast is False
    assert wlan.client_isolation is True
    assert wlan.vlan.vlan_id == 30
    assert wlan.vlan.dynamic_vlan_mode == 2
    assert wlan.vlan.dhcp_option82 is not None
    assert wlan.vlan.dhcp_option82.enabled is True
    assert wlan.vlan.dhcp_option82.circuit_id == (1, 2)
    assert wlan.security.psk_configured is True
    assert wlan.security.fast_roaming is True
    assert wlan.portal.enabled is True

    assert update.management_vlan is not None
    assert update.management_vlan.enabled is True
    assert update.management_vlan.vlan_id == 99
    assert update.portal_free_policy is not None
    assert len(update.portal_free_policy.layer2_rules) == 1
    assert len(update.portal_free_policy.url_rules) == 1


def test_parse_set_request_requires_object_body():
    with pytest.raises(ValueError, match="SET_REQUEST body"):
        parse_set_request({"body": []})


def test_parse_ssid_rejects_invalid_vlan():
    with pytest.raises(ValueError, match="VLAN ID"):
        parse_config_body({"ssid_5G": {"ssid": [{"ssidName": "bad", "vlanId": 5000}]}})


def test_parse_ssid_vlan_zero_as_no_vlan():
    update = parse_config_body(
        {"ssid_2G": {"ssid": [{"ssidName": "corp", "vlanId": 0}]}}
    )

    assert update.wlans[0].vlan.vlan_id is None


def test_parse_disabled_mac_auth_as_no_radius_request():
    update = parse_config_body(
        {
            "ssid_2G": {
                "ssid": [
                    {
                        "ssidName": "guest",
                        "macAuth": {"enable": False},
                    }
                ]
            }
        }
    )

    assert update.wlans[0].security.radius_mac_auth is None


def test_parse_wifi_control_led_config():
    update = parse_config_body({"wifiControlLed": {"enable": "off", "isPressed": True}})

    assert update.wifi_control_led is not None
    assert update.wifi_control_led.enabled is False
    assert update.wifi_control_led.is_pressed is True


def test_parse_client_config_operation_and_rate_limit_models():
    update = parse_config_body(
        {
            "clientConfig": [{"clientMac": "aa:bb:cc:dd:ee:ff", "unauth": True}],
            "clientOperation_cmd": [
                {"clientMac": "aa:bb:cc:dd:ee:ff", "operation": 2},
            ],
            "clientOperation": [
                {
                    "clientMac": "02:00:00:00:00:02",
                    "operation": 3,
                    "ssid": "guest",
                    "radioId": 1,
                }
            ],
            "clientRateConfig": {
                "action": 0,
                "clientRateLimit": [
                    {"mac": "aa:bb:cc:dd:ee:ff", "down": 1024, "up": 512}
                ],
            },
        }
    )

    assert update.unhandled_keys == ()
    assert update.client_configs[0].client_mac == "aa:bb:cc:dd:ee:ff"
    assert update.client_configs[0].unauthenticated is True

    assert update.client_operations[0].source_key == "clientOperation"
    assert update.client_operations[0].operation_code is ClientOperationCode.PORTAL_UNAUTH
    assert update.client_operations[0].ssid == "guest"
    assert update.client_operations[0].radio_id == 1
    assert update.client_operations[1].source_key == "clientOperation_cmd"
    assert update.client_operations[1].operation_code is ClientOperationCode.RECONNECT

    assert update.client_rate_config is not None
    assert update.client_rate_config.action == 0
    assert update.client_rate_config.limits[0].mac == "aa:bb:cc:dd:ee:ff"
    assert update.client_rate_config.limits[0].down == 1024
    assert update.client_rate_config.limits[0].up == 512


def test_parse_client_operation_requires_client_mac():
    with pytest.raises(ValueError, match="clientOperation.clientMac"):
        parse_config_body({"clientOperation": [{"operation": 2}]})


def test_parse_initial_controller_defaults_as_ack_only_config():
    update = parse_config_body(
        {
            "lanSetting": {
                "connType": 1,
                "useFallBack": True,
                "fallBackIp": "192.168.0.254",
                "fallBackMask": "255.255.255.0",
            },
            "macFilterGlobal": {"enable": True},
            "schedulerGlobal": {"enable": True, "mode": 0},
            "logSetting": {"mailEnable": False, "logServerEnable": False},
            "ssh": {"sshenable": "on", "sshserverPort": 22, "layer3Access": True},
            "ipGroup": {"ipGroups": [{"ipSubnets": ["0.0.0.0/0"]}]},
            "ipv6Group": {"ipv6Groups": [{"ipv6Subnets": ["::/0"]}]},
            "snmp": {"v1v2cEnable": 0, "v3Enable": 0},
            "lldp": {"enable": 1},
        }
    )

    assert update.unhandled_keys == ()
    assert update.ack_only_keys == (
        "ipGroup",
        "ipv6Group",
        "lanSetting",
        "lldp",
        "logSetting",
        "macFilterGlobal",
        "schedulerGlobal",
        "snmp",
        "ssh",
    )


def test_parse_scheduler_and_wireless_advanced_as_passive_config():
    update = parse_config_body(
        {
            "schedulerAssoc": [{"id": 1, "profileId": 2}],
            "wirelessAdv_2G": {"radioId": 0, "dtimPeriod": 1, "beaconInterval": 100},
        }
    )

    assert update.unhandled_keys == ()
    assert update.passive_keys == ("schedulerAssoc", "wirelessAdv_2G")


def test_validate_ssid_rejects_names_over_32_bytes():
    with pytest.raises(ValueError, match="32 UTF-8 bytes"):
        validate_ssid_name("x" * 33)


def test_validate_vlan_id_accepts_valid_range():
    assert validate_vlan_id(1) == 1
    assert validate_vlan_id(4094) == 4094
