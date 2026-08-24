from open_omada_device_agent.ap_config import parse_config_body
from open_omada_device_agent.device_commands import SysfsLedAdapter
from open_omada_device_agent.platform_capabilities import PlatformCapabilities


def _caps(**overrides):
    values = {"platform": "generic", "supports_led_control": True}
    values.update(overrides)
    return PlatformCapabilities(**values)


def test_sysfs_led_adapter_writes_configured_brightness_path(tmp_path):
    brightness = tmp_path / "brightness"
    update = parse_config_body({"led": {"enable": "off"}})

    result = SysfsLedAdapter(
        brightness_path=str(brightness),
        on_value="255",
        off_value="0",
    ).reconcile(update, _caps())

    assert result.applied is True
    assert result.changed is True
    assert brightness.read_text(encoding="ascii") == "0\n"


def test_sysfs_led_adapter_rejects_led_when_capability_is_disabled(tmp_path):
    update = parse_config_body({"led": {"enable": "on"}})

    result = SysfsLedAdapter(brightness_path=str(tmp_path / "brightness")).reconcile(
        update,
        _caps(supports_led_control=False),
    )

    assert result.applied is False
    assert "LED control requested" in result.error


def test_sysfs_led_adapter_rejects_locate_until_trigger_is_implemented(tmp_path):
    update = parse_config_body({"led": {"locate": True}})

    result = SysfsLedAdapter(brightness_path=str(tmp_path / "brightness")).reconcile(
        update,
        _caps(),
    )

    assert result.applied is False
    assert "LED locate reconciliation is not implemented" in result.error


def test_sysfs_led_adapter_rejects_wifi_control_led_until_implemented(tmp_path):
    update = parse_config_body({"wifiControlLed": {"enable": "on"}})

    result = SysfsLedAdapter(brightness_path=str(tmp_path / "brightness")).reconcile(
        update,
        _caps(),
    )

    assert result.applied is False
    assert "WiFi control LED reconciliation is not implemented" in result.error
