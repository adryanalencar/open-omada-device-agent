import pytest

from open_omada_device_agent.ap_config import parse_config_body, parse_set_request
from open_omada_device_agent.domain import RadioBand, validate_ssid_name, validate_vlan_id


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
    assert update.unhandled_keys == ("led",)

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


def test_validate_ssid_rejects_names_over_32_bytes():
    with pytest.raises(ValueError, match="32 UTF-8 bytes"):
        validate_ssid_name("x" * 33)


def test_validate_vlan_id_accepts_valid_range():
    assert validate_vlan_id(1) == 1
    assert validate_vlan_id(4094) == 4094
