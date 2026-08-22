import time

from open_omada_device_agent.adoption import _device_negotiation_body, _inform_body, _preconnect_body, _set_response_body
from open_omada_device_agent.discovery import build_discovery
from open_omada_device_agent.capabilities import AP_COMPONENTS_V2


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
    body = _inform_body(need_reply=True, started_at=time.monotonic() - 5)

    assert body["needReply"] == 1
    assert body["deviceInfo"]["isFactory"] is False
    assert int(body["deviceInfo"]["upTime"]) >= 4
    assert body["deviceInfo"]["model"]


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
    body = _inform_body(need_reply=False, started_at=time.monotonic())

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
