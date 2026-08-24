import time

from open_omada_device_agent import config
from open_omada_device_agent.bootstrap import build_runtime
from open_omada_device_agent.adoption import (
    CONFIG_ERROR,
    _apply_config_update,
    _describe_config_update,
    _device_negotiation_body,
    _get_response_body,
    _project_inform_body,
    _notify_reply_body,
    _preconnect_body,
    _send_forget_response,
    _send_get_response,
    _send_notify_reply,
    _set_response_body,
)
from open_omada_device_agent.discovery import build_discovery
from open_omada_device_agent.capabilities import AP_COMPONENTS_V2
from open_omada_device_agent.ap_config import parse_config_body
from open_omada_device_agent.ecsp import MessageType, decode_frame


class RecordingSocket:
    def __init__(self):
        self.sent = b""

    def sendall(self, data):
        self.sent += data


def test_device_negotiation_has_required_non_null_v2_fields():
    body = _device_negotiation_body("0123456789abcdef0123456789abcdef")

    assert body["configVersion"] == 0
    assert body["devCap"] == {}
    assert body["components_v2"] == AP_COMPONENTS_V2
    assert body["components_v2"]
    assert body["radioCap"] == []
    assert body["channelInfo"] == []
    assert body["controllerSetting"] == {
        "controllerId": "0123456789abcdef0123456789abcdef"
    }
    assert body["deviceInfo"]["model"]
    assert "ip" not in body["deviceInfo"]
    assert "isFactory" not in body["deviceInfo"]
    assert isinstance(body["deviceMisc"], dict)


def test_advertised_v2_component_versions_have_ecsp_major_minor_shape():
    for name, version in AP_COMPONENTS_V2.items():
        major, minor = version.split(".")
        assert name
        assert major.isdigit()
        assert minor.isdigit()


def test_post_adoption_inform_is_not_factory_and_requests_reply_when_asked():
    body = _project_inform_body(services=build_runtime(), need_reply=True, started_at=time.monotonic() - 5)

    assert body["needReply"] == 1
    assert body["deviceInfo"]["isFactory"] is False
    assert int(body["deviceInfo"]["upTime"]) >= 4
    assert body["deviceInfo"]["model"]


def test_inform_includes_real_dhcp_lease_clients_when_available(tmp_path, monkeypatch):
    leases = tmp_path / "dhcp.leases"
    leases.write_text(
        "1000 aa:bb:cc:dd:ee:ff 192.0.2.10 phone *\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "DHCP_LEASE_FILE", str(leases))
    monkeypatch.setattr(
        "open_omada_device_agent.bootstrap.runtime.collect_openwrt_wireless_clients",
        lambda: (),
    )

    from open_omada_device_agent.bootstrap import build_runtime
    build_runtime.cache_clear()
    body = _project_inform_body(services=build_runtime(), need_reply=False, started_at=time.monotonic())

    assert body["clients"][0]["mac"] == "aa:bb:cc:dd:ee:ff"
    assert body["clients"][0]["ip"] == "192.0.2.10"
    assert body["clients"][0]["name"] == "phone"


def test_managed_reconnect_preconnect_uses_v2_rebuild_shape():
    controller_id = "0123456789abcdef0123456789abcdef"
    body = _preconnect_body(controller_id, managed_reconnect=True)

    assert body["rebuild"] == 1
    assert body["deviceInfo"]["isFactory"] is False
    assert body["controllerSetting"]["controllerId"] == controller_id


def test_first_adoption_preconnect_keeps_prelink_shape():
    controller_id = "0123456789abcdef0123456789abcdef"
    body = _preconnect_body(controller_id)

    assert body["rebuild"] == 0
    assert body["controllerSetting"]["controllerId"] == controller_id


def test_inform_reports_minimal_wired_lan_info():
    body = _project_inform_body(services=build_runtime(), need_reply=False, started_at=time.monotonic())

    assert float(body["lanInfo"]["rate"]) > 0
    assert isinstance(body["lanInfo"]["duplex"], int)
    assert body["lanInfo"]["port"]


def test_set_response_uses_request_body_sequence_and_config_version():
    request = {
        "header": {"seq": 77, "type": 4096},
        "body": {
            "sequenceId": 2,
            "configVersion": 1,
            "led": {"enable": "on"},
        },
    }

    assert _set_response_body(request) == {
        "sequenceId": 2,
        "errcode": 0,
        "configVersion": 1,
    }


def test_set_response_can_report_local_config_failure_without_advancing_version():
    request = {
        "header": {"seq": 88, "type": 4096},
        "body": {
            "sequenceId": 14,
            "configVersionInc": 1,
            "ssid_2G": {"ssid": [{"ssidName": "unsupported"}]},
        },
    }

    assert _set_response_body(
        request, current_config_version=2, errcode=CONFIG_ERROR
    ) == {
        "sequenceId": 14,
        "errcode": 1,
        "configVersion": 2,
    }


def test_set_response_derives_absolute_version_from_config_version_inc():
    request = {
        "header": {"seq": 88, "type": 4096},
        "body": {
            "sequenceId": 14,
            "configVersionInc": 1,
            "led": {"enable": "on", "locate": False},
        },
    }

    assert _set_response_body(request, current_config_version=2) == {
        "sequenceId": 14,
        "errcode": 0,
        "configVersion": 3,
    }


def test_forget_response_uses_confirmed_response_type_without_seq():
    sock = RecordingSocket()

    response_type = _send_forget_response(
        sock,
        {"header": {"type": int(MessageType.FORGET_REQUEST), "seq": 99}},
        controller_id="controller-id",
        dump_json=False,
    )

    message = decode_frame(sock.sent)
    assert response_type is MessageType.FORGET_RESPONSE
    assert message["header"]["type"] == int(MessageType.FORGET_RESPONSE)
    assert "seq" not in message["header"]
    assert message["header"]["dest"] == "controller-id"
    assert message["body"] == {}


def test_forget_no_reset_response_uses_no_reset_type():
    sock = RecordingSocket()

    response_type = _send_forget_response(
        sock,
        {"header": {"type": int(MessageType.FORGET_REQUEST_NO_RESET), "seq": 99}},
        controller_id="controller-id",
        dump_json=False,
    )

    message = decode_frame(sock.sent)
    assert response_type is MessageType.FORGET_RESPONSE_NO_RESET
    assert message["header"]["type"] == int(MessageType.FORGET_RESPONSE_NO_RESET)
    assert "seq" not in message["header"]


def test_get_response_reports_unsupported_keys_without_success():
    request = {
        "header": {"type": int(MessageType.GET_REQUEST), "seq": 42},
        "body": {"sequenceId": 12, "powerControl": {}},
    }

    assert _get_response_body(request) == {
        "sequenceId": 12,
        "errcode": 1,
        "unsupportedKeys": ["powerControl"],
    }


def test_send_get_response_preserves_header_sequence():
    sock = RecordingSocket()

    sequence_id, errcode = _send_get_response(
        sock,
        {
            "header": {"type": int(MessageType.GET_REQUEST), "seq": 42},
            "body": {"sequenceId": 12, "gps": {}},
        },
        controller_id="controller-id",
        dump_json=False,
    )

    message = decode_frame(sock.sent)
    assert sequence_id == 12
    assert errcode == 1
    assert message["header"]["type"] == int(MessageType.GET_RESPONSE)
    assert message["header"]["seq"] == 42
    assert message["body"]["unsupportedKeys"] == ["gps"]


def test_notify_reply_body_preserves_notify_id_and_subject():
    request = {
        "header": {"type": int(MessageType.NOTIFY_REQUEST), "seq": 7},
        "body": {"nid": 99, "sub": 15, "ctnt": {"value": True}},
    }

    assert _notify_reply_body(request) == {
        "nid": 99,
        "sub": 15,
        "err": 1,
        "rst": {"error": "unsupported notify request"},
    }


def test_send_notify_reply_uses_v2_reply_for_v2_request():
    sock = RecordingSocket()

    replied = _send_notify_reply(
        sock,
        {
            "header": {"type": int(MessageType.NOTIFY_REQUEST_V2), "seq": 7},
            "body": {"nid": 99, "sub": 15, "ctnt": {"value": True}},
        },
        controller_id="controller-id",
        dump_json=False,
    )

    message = decode_frame(sock.sent)
    assert replied is True
    assert message["header"]["type"] == int(MessageType.NOTIFY_REPLY_V2)
    assert message["header"]["seq"] == 7
    assert message["body"]["nid"] == 99
    assert message["body"]["sub"] == 15
    assert message["body"]["err"] == 1


def test_send_notify_reply_honors_no_reply_flag():
    sock = RecordingSocket()

    replied = _send_notify_reply(
        sock,
        {
            "header": {"type": int(MessageType.NOTIFY_REQUEST), "seq": 7},
            "body": {"nid": 99, "sub": 15, "nre": 1},
        },
        controller_id="controller-id",
        dump_json=False,
    )

    assert replied is False
    assert sock.sent == b""


def test_set_response_rejects_increment_when_current_version_is_unknown():
    request = {
        "header": {"seq": 89, "type": 4096},
        "body": {"sequenceId": 15, "configVersionInc": 1},
    }

    try:
        _set_response_body(request)
    except RuntimeError as exc:
        assert "local config version is unknown" in str(exc)
    else:
        raise AssertionError("incremental SET without a current version must fail")


def test_device_negotiation_reports_persisted_config_version_on_reconnect():
    body = _device_negotiation_body("controller-id", config_version=7)
    assert body["configVersion"] == 7


def test_managed_rediscovery_is_not_factory_new():
    msg = build_discovery(
        1,
        "0123456789abcdef0123456789abcdef",
        "0123456789abcdef01234567",
        managed_restart=True,
    )
    assert msg["body"]["deviceInfo"]["isFactory"] is False
    assert msg["header"]["dest"] == "0123456789abcdef01234567"


def test_initial_discovery_keeps_factory_identity():
    msg = build_discovery(
        1,
        "0123456789abcdef0123456789abcdef",
        "0123456789abcdef01234567",
    )
    assert msg["body"]["deviceInfo"]["isFactory"] is True


def test_describe_config_update_reports_domains_without_secrets():
    update = parse_config_body(
        {
            "sequenceId": 10,
            "configVersionInc": 1,
            "wirelessBasic_2G": {"radioId": 1, "radioEnable": True},
            "ssid_2G": {
                "radioId": 1,
                "ssid": [{"ssidName": "private", "pskKey": "do-not-log"}],
            },
            "managementVlan": {
                "managementVlanEnable": "on",
                "managementVlanId": 20,
            },
            "portalFreePolicyConfig": {
                "portalFreePolicy": [{}],
                "urlPortalFreePolicy": [{}, {}],
            },
        }
    )

    description = _describe_config_update(update)

    assert "sequenceId=10" in description
    assert "radios=1[2g]" in description
    assert "wlans=1[2g]" in description
    assert "managementVlan=on:20" in description
    assert "portalFreePolicy=l2:1,url:2" in description
    assert "private" not in description
    assert "do-not-log" not in description


def test_apply_config_update_rejects_unhandled_keys_without_fake_ack():
    update = parse_config_body({"unsupportedCommand": {"enabled": True}})

    assert _apply_config_update(update, services=build_runtime()) == CONFIG_ERROR
