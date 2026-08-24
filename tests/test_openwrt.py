from dataclasses import dataclass, field

from open_omada_device_agent.ap_config import parse_config_body
from open_omada_device_agent.domain import RadioBand
from open_omada_device_agent.openwrt import CommandResult, OpenWrtUciAdapter, build_uci_batch
from open_omada_device_agent.platform_capabilities import PlatformCapabilities


@dataclass
class RecordingRunner:
    calls: list[tuple[tuple[str, ...], str | None]] = field(default_factory=list)
    fail_wifi_reload: bool = False

    def run(self, args, *, input_text=None):
        self.calls.append((tuple(args), input_text))
        if self.fail_wifi_reload and tuple(args) == ("wifi", "reload"):
            return CommandResult(returncode=1, stderr="reload failed")
        return CommandResult(returncode=0)


def _caps(**overrides):
    values = {
        "platform": "openwrt",
        "radio_bands": (RadioBand.TWO_G, RadioBand.FIVE_G),
        "max_ssids": 4,
        "supports_wlan_config": True,
        "supports_wpa2_psk": True,
    }
    values.update(overrides)
    return PlatformCapabilities(**values)


def test_builds_idempotent_uci_batch_for_radio_and_psk_wlan():
    update = parse_config_body(
        {
            "wirelessBasic_2G": {
                "radioId": 0,
                "radioEnable": True,
                "channel": 11,
                "chanWidth": 20,
                "txPower": 14,
            },
            "ssid_2G": {
                "radioId": 0,
                "ssid": [
                    {
                        "index": 1,
                        "ssidName": "Open Omada",
                        "ssidBcast": True,
                        "ssidIsolation": False,
                        "pskVer": 2,
                        "pskKey": "network-passphrase",
                    }
                ],
            },
        }
    )

    batch = build_uci_batch(update, _caps())

    assert "set wireless.radio0.disabled='0'" in batch
    assert "set wireless.radio0.channel='11'" in batch
    assert "set wireless.radio0.htmode='HT20'" in batch
    assert "delete wireless.openomada_2g_1" in batch
    assert "set wireless.openomada_2g_1=wifi-iface" in batch
    assert "set wireless.openomada_2g_1.ssid='Open Omada'" in batch
    assert "set wireless.openomada_2g_1.encryption='psk2'" in batch
    assert "set wireless.openomada_2g_1.key='network-passphrase'" in batch
    assert batch[-1] == "commit wireless"


def test_reconcile_runs_uci_batch_and_wifi_reload_without_shell():
    update = parse_config_body(
        {"ssid_2G": {"radioId": 0, "ssid": [{"ssidName": "lab", "pskKey": "secret"}]}}
    )
    runner = RecordingRunner()

    result = OpenWrtUciAdapter(runner).reconcile(update, _caps())

    assert result.applied is True
    assert result.changed is True
    assert runner.calls[0][0] == ("uci", "-q", "batch")
    assert runner.calls[0][1] is not None
    assert runner.calls[1] == (("wifi", "reload"), None)


def test_reconcile_rejects_vlan_when_capability_is_disabled():
    update = parse_config_body(
        {"ssid_2G": {"radioId": 0, "ssid": [{"ssidName": "lab", "vlanId": 30}]}}
    )
    runner = RecordingRunner()

    result = OpenWrtUciAdapter(runner).reconcile(update, _caps())

    assert result.applied is False
    assert "SSID VLAN requested" in result.error
    assert runner.calls == []


def test_reconcile_reports_wifi_reload_failure():
    update = parse_config_body(
        {"ssid_2G": {"radioId": 0, "ssid": [{"ssidName": "lab", "pskKey": "secret"}]}}
    )
    runner = RecordingRunner(fail_wifi_reload=True)

    result = OpenWrtUciAdapter(runner).reconcile(update, _caps())

    assert result.applied is False
    assert result.changed is True
    assert result.error == "reload failed"
