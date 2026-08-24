import pytest

from open_omada_device_agent.domain import RadioBand
from open_omada_device_agent.platform_capabilities import (
    capability_summary,
    detect_platform_capabilities,
)


def test_detects_openwrt_wlan_capability_from_tools():
    def which(name):
        return f"/sbin/{name}" if name in {"uci", "ubus", "nft", "hostapd"} else None

    caps = detect_platform_capabilities(
        env={
            "OMADA_PLATFORM": "auto",
            "OMADA_RADIO_BANDS": "2g,5g",
            "OMADA_MAX_SSIDS": "8",
        },
        command_exists=which,
    )

    assert caps.platform == "openwrt"
    assert caps.has_uci is True
    assert caps.has_ubus is True
    assert caps.has_nft is True
    assert caps.has_dnsmasq is False
    assert caps.radio_bands == (RadioBand.TWO_G, RadioBand.FIVE_G)
    assert caps.max_ssids == 8
    assert caps.supports_wlan_config is True
    assert caps.supports_wpa2_psk is True
    assert caps.supports_portal is False
    assert caps.supports_dynamic_vlan is False
    assert caps.supports_client_operations is True


def test_capability_overrides_do_not_infer_unsupported_features():
    caps = detect_platform_capabilities(
        env={
            "OMADA_PLATFORM": "generic",
            "OMADA_CAP_WLAN": "true",
            "OMADA_CAP_DYNAMIC_VLAN": "true",
            "OMADA_CAP_PORTAL": "true",
        },
        command_exists=lambda _name: None,
    )

    assert caps.platform == "generic"
    assert caps.supports_wlan_config is True
    assert caps.supports_dynamic_vlan is True
    assert caps.supports_portal is True


def test_led_capability_is_enabled_by_configured_brightness_path():
    caps = detect_platform_capabilities(
        env={
            "OMADA_PLATFORM": "generic",
            "OMADA_LED_BRIGHTNESS_PATH": "/sys/class/leds/status/brightness",
        },
        command_exists=lambda _name: None,
    )

    assert caps.supports_led_control is True


def test_client_rate_limit_capability_remains_opt_in():
    caps = detect_platform_capabilities(
        env={
            "OMADA_PLATFORM": "openwrt",
            "OMADA_CAP_CLIENT_RATE_LIMITS": "true",
        },
        command_exists=lambda name: f"/sbin/{name}" if name == "ubus" else None,
    )

    assert caps.supports_client_operations is True
    assert caps.supports_client_rate_limits is True


def test_capability_summary_is_secret_free_and_stable():
    caps = detect_platform_capabilities(
        env={"OMADA_PLATFORM": "generic", "OMADA_CAP_RADIUS": "true"},
        command_exists=lambda _name: None,
    )

    summary = capability_summary(caps)

    assert "platform=generic" in summary
    assert "radius" in summary
    assert "password" not in summary.lower()
    assert "secret" not in summary.lower()


def test_rejects_unknown_platform_and_radio_band():
    with pytest.raises(ValueError, match="OMADA_PLATFORM"):
        detect_platform_capabilities(env={"OMADA_PLATFORM": "linux"})

    with pytest.raises(ValueError, match="OMADA_RADIO_BANDS"):
        detect_platform_capabilities(env={"OMADA_RADIO_BANDS": "7g"})
