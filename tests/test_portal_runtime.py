from dataclasses import dataclass, field

from open_omada_device_agent.ap_config import parse_config_body
from open_omada_device_agent.openwrt import CommandResult
from open_omada_device_agent.platform_capabilities import PlatformCapabilities
from open_omada_device_agent.portal_runtime import OpenWrtPortalRuntime


@dataclass
class RecordingRunner:
    calls: list[tuple[tuple[str, ...], str | None]] = field(default_factory=list)
    table_exists: bool = False

    def run(self, args, *, input_text=None):
        command = tuple(args)
        self.calls.append((command, input_text))
        if command == ("nft", "list", "table", "inet", "openomada_portal"):
            return CommandResult(returncode=0 if self.table_exists else 1)
        return CommandResult(returncode=0)


def _caps(**overrides):
    values = {
        "platform": "openwrt",
        "has_nft": True,
        "max_ssids": 4,
        "supports_portal": True,
    }
    values.update(overrides)
    return PlatformCapabilities(**values)


def test_portal_runtime_applies_nft_policy_for_portal_wlan_and_free_policy():
    update = parse_config_body(
        {
            "ssid_2G": {"ssid": [{"ssidName": "guest", "portal": True}]},
            "portalFreePolicyConfig": {
                "portalFreePolicy": [
                    {"value": "192.0.2.10"},
                    {"value": "not-an-ip"},
                ],
            },
        }
    )
    runner = RecordingRunner(table_exists=False)

    result = OpenWrtPortalRuntime(
        runner,
        interface="wlan0",
        redirect_port=8080,
    ).reconcile(update, _caps())

    assert result.applied is True
    assert result.changed is True
    assert runner.calls[0][0] == ("nft", "list", "table", "inet", "openomada_portal")
    assert runner.calls[1][0] == ("nft", "-f", "-")
    assert "iifname \"wlan0\" tcp dport 80 redirect to :8080" in (
        runner.calls[1][1] or ""
    )
    assert "192.0.2.10" in (runner.calls[1][1] or "")
    assert "not-an-ip" not in (runner.calls[1][1] or "")


def test_portal_runtime_rejects_missing_interface():
    update = parse_config_body(
        {"ssid_2G": {"ssid": [{"ssidName": "guest", "portal": True}]}}
    )

    result = OpenWrtPortalRuntime(RecordingRunner(), interface="").reconcile(
        update,
        _caps(),
    )

    assert result.applied is False
    assert "OMADA_PORTAL_INTERFACE" in result.error


def test_portal_runtime_noops_without_portal_config():
    update = parse_config_body({"ssid_2G": {"ssid": [{"ssidName": "corp"}]}})
    runner = RecordingRunner()

    result = OpenWrtPortalRuntime(runner, interface="wlan0").reconcile(update, _caps())

    assert result.applied is True
    assert result.changed is False
    assert runner.calls == []


def test_portal_runtime_ignores_portal_wlan_beyond_platform_limit():
    update = parse_config_body(
        {
            "ssid_2G": {
                "ssid": [
                    {"ssidName": "corp"},
                    {"ssidName": "guest", "portal": True},
                ]
            }
        }
    )
    runner = RecordingRunner()

    result = OpenWrtPortalRuntime(runner, interface="wlan0").reconcile(
        update,
        _caps(max_ssids=1),
    )

    assert result.applied is True
    assert result.changed is False
    assert runner.calls == []


def test_portal_runtime_noops_for_free_policy_without_portal_wlan():
    update = parse_config_body(
        {"portalFreePolicyConfig": {"portalFreePolicy": [{"value": "192.0.2.10"}]}}
    )
    runner = RecordingRunner()

    result = OpenWrtPortalRuntime(runner, interface="wlan0").reconcile(
        update,
        _caps(supports_portal=False, has_nft=False),
    )

    assert result.applied is True
    assert result.changed is False
    assert runner.calls == []
