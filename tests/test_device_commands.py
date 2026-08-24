from open_omada_device_agent.ap_config import parse_config_body
from dataclasses import dataclass, field

from open_omada_device_agent.device_commands import (
    OpenWrtClientControlAdapter,
    SysfsLedAdapter,
    build_client_block_nftables_rules,
    build_client_rate_limit_nftables_rules,
)
from open_omada_device_agent.openwrt import CommandResult
from open_omada_device_agent.platform_capabilities import PlatformCapabilities


def _caps(**overrides):
    values = {
        "platform": "generic",
        "has_nft": True,
        "has_ubus": True,
        "supports_client_operations": True,
        "supports_led_control": True,
    }
    values.update(overrides)
    return PlatformCapabilities(**values)


@dataclass
class RecordingRunner:
    calls: list[tuple[tuple[str, ...], str | None]] = field(default_factory=list)
    client_table_exists: bool = True
    client_rate_table_exists: bool = True

    def run(self, args, *, input_text=None):
        command = tuple(args)
        self.calls.append((command, input_text))
        if command == ("nft", "list", "table", "bridge", "openomada_clients"):
            return CommandResult(returncode=0 if self.client_table_exists else 1)
        if command == ("nft", "list", "table", "bridge", "openomada_client_rates"):
            return CommandResult(returncode=0 if self.client_rate_table_exists else 1)
        return CommandResult(returncode=0)


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


def test_sysfs_led_adapter_rejects_locate_without_trigger_path(tmp_path):
    update = parse_config_body({"led": {"locate": True}})

    result = SysfsLedAdapter(brightness_path=str(tmp_path / "brightness")).reconcile(
        update,
        _caps(),
    )

    assert result.applied is False
    assert "LED trigger path is not configured" in result.error


def test_sysfs_led_adapter_writes_locate_trigger(tmp_path):
    trigger = tmp_path / "trigger"
    update = parse_config_body({"led": {"locate": True}})

    result = SysfsLedAdapter(
        trigger_path=str(trigger),
        locate_trigger="timer",
        default_trigger="none",
    ).reconcile(update, _caps())

    assert result.applied is True
    assert result.changed is True
    assert trigger.read_text(encoding="ascii") == "timer\n"


def test_sysfs_led_adapter_restores_default_trigger_when_locate_stops(tmp_path):
    trigger = tmp_path / "trigger"
    update = parse_config_body({"led": {"locate": False}})

    result = SysfsLedAdapter(
        trigger_path=str(trigger),
        locate_trigger="timer",
        default_trigger="default-on",
    ).reconcile(update, _caps())

    assert result.applied is True
    assert trigger.read_text(encoding="ascii") == "default-on\n"


def test_sysfs_led_adapter_rejects_wifi_control_led_until_implemented(tmp_path):
    update = parse_config_body({"wifiControlLed": {"enable": "on"}})

    result = SysfsLedAdapter(brightness_path=str(tmp_path / "brightness")).reconcile(
        update,
        _caps(),
    )

    assert result.applied is False
    assert "WiFi control LED reconciliation is not implemented" in result.error


def test_openwrt_client_control_reconnects_client_through_hostapd_ubus():
    update = parse_config_body(
        {"clientOperation_cmd": [{"clientMac": "AA-BB-CC-DD-EE-FF", "operation": 2}]}
    )
    runner = RecordingRunner()

    result = OpenWrtClientControlAdapter(
        runner,
        hostapd_iface="wlan0",
        block_interface="br-guest",
    ).reconcile(update, _caps())

    assert result.applied is True
    assert result.changed is True
    assert runner.calls == [
        (
            (
                "ubus",
                "call",
                "hostapd.wlan0",
                "del_client",
                '{"addr":"aa:bb:cc:dd:ee:ff","reason":5,"deauth":true,"ban_time":0}',
            ),
            None,
        )
    ]


def test_openwrt_client_control_blocks_client_with_bridge_nftables():
    update = parse_config_body(
        {"clientOperation": [{"clientMac": "aa:bb:cc:dd:ee:ff", "operation": 0}]}
    )
    runner = RecordingRunner(client_table_exists=False)

    result = OpenWrtClientControlAdapter(
        runner,
        hostapd_iface="wlan0",
        block_interface="br-guest",
    ).reconcile(update, _caps())

    assert result.applied is True
    assert result.changed is True
    assert runner.calls[0][0] == ("nft", "list", "table", "bridge", "openomada_clients")
    assert runner.calls[1][0] == ("nft", "-f", "-")
    assert "table bridge openomada_clients" in (runner.calls[1][1] or "")
    assert runner.calls[2] == (
        (
            "nft",
            "add",
            "element",
            "bridge",
            "openomada_clients",
            "blocked_macs",
            "{",
            "aa:bb:cc:dd:ee:ff",
            "}",
        ),
        None,
    )


def test_openwrt_client_control_rejects_lock_to_ap_operation():
    update = parse_config_body(
        {"clientOperation": [{"clientMac": "aa:bb:cc:dd:ee:ff", "operation": 6}]}
    )

    result = OpenWrtClientControlAdapter(
        RecordingRunner(),
        hostapd_iface="wlan0",
        block_interface="br-guest",
    ).reconcile(update, _caps())

    assert result.applied is False
    assert "LOCK_TO_AP_BLOCK" in result.error


def test_openwrt_client_control_applies_rate_limits_with_bridge_nftables():
    update = parse_config_body(
        {
            "clientRateConfig": {
                "action": 0,
                "clientRateLimit": [{"mac": "aa:bb:cc:dd:ee:ff", "down": 1024, "up": 512}],
            }
        }
    )
    runner = RecordingRunner(client_rate_table_exists=True)

    result = OpenWrtClientControlAdapter(
        runner,
        hostapd_iface="wlan0",
        block_interface="br-guest",
        rate_limit_interface="wlan0",
    ).reconcile(update, _caps(supports_client_rate_limits=True))

    assert result.applied is True
    assert result.changed is True
    assert runner.calls[0][0] == (
        "nft",
        "list",
        "table",
        "bridge",
        "openomada_client_rates",
    )
    assert runner.calls[1][0] == (
        "nft",
        "delete",
        "table",
        "bridge",
        "openomada_client_rates",
    )
    assert runner.calls[2][0] == ("nft", "-f", "-")
    assert "ether saddr aa:bb:cc:dd:ee:ff limit rate over 64000 bytes/second drop" in (
        runner.calls[2][1] or ""
    )
    assert "ether daddr aa:bb:cc:dd:ee:ff limit rate over 128000 bytes/second drop" in (
        runner.calls[2][1] or ""
    )


def test_openwrt_client_control_rejects_rate_limits_when_capability_is_disabled():
    update = parse_config_body(
        {
            "clientRateConfig": {
                "action": 0,
                "clientRateLimit": [{"mac": "aa:bb:cc:dd:ee:ff", "down": 1, "up": 1}],
            }
        }
    )

    result = OpenWrtClientControlAdapter(
        RecordingRunner(),
        hostapd_iface="wlan0",
        block_interface="br-guest",
        rate_limit_interface="wlan0",
    ).reconcile(update, _caps(supports_client_rate_limits=False))

    assert result.applied is False
    assert "client rate-limit requested" in result.error


def test_build_client_block_nftables_rules_validates_interface():
    rules = build_client_block_nftables_rules("br-guest")

    assert "iifname \"br-guest\" ether saddr @blocked_macs drop" in rules


def test_build_client_rate_limit_nftables_rules_converts_kbps_to_bytes_per_second():
    update = parse_config_body(
        {
            "clientRateConfig": {
                "clientRateLimit": [{"mac": "aa:bb:cc:dd:ee:ff", "down": 8, "up": 16}]
            }
        }
    )

    rules = build_client_rate_limit_nftables_rules("wlan0", update.client_rate_config)

    assert "limit rate over 2000 bytes/second drop" in rules
    assert "limit rate over 1000 bytes/second drop" in rules
