from dataclasses import dataclass, field

from open_omada_device_agent.ap_config import parse_config_body
from open_omada_device_agent.domain import RadioBand
import open_omada_device_agent.openwrt as openwrt
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


def test_builds_network_interface_for_enabled_ssid_vlan_capability():
    update = parse_config_body(
        {"ssid_2G": {"radioId": 0, "ssid": [{"ssidName": "lab", "vlanId": 30}]}}
    )

    batch = build_uci_batch(update, _caps(supports_ssid_vlan=True))

    assert "delete network.openomada_vlan30" in batch
    assert "set network.openomada_vlan30=interface" in batch
    assert "set network.openomada_vlan30.device='br-lan.30'" in batch
    assert "commit network" in batch
    assert "set wireless.openomada_2g_lab.network='openomada_vlan30'" in batch


def test_builds_management_vlan_device_mapping_when_configured(monkeypatch):
    monkeypatch.setattr(openwrt.config, "MANAGEMENT_VLAN_INTERFACE", "lan")
    monkeypatch.setattr(openwrt.config, "MANAGEMENT_VLAN_DEVICE", "br-lan")
    update = parse_config_body(
        {"managementVlan": {"managementVlanEnable": "on", "managementVlanId": 99}}
    )

    batch = build_uci_batch(update, _caps(supports_management_vlan=True))

    assert "set network.lan.device='br-lan.99'" in batch
    assert "commit network" in batch


def test_reconcile_rejects_enabled_management_vlan_without_target(monkeypatch):
    monkeypatch.setattr(openwrt.config, "MANAGEMENT_VLAN_INTERFACE", "")
    monkeypatch.setattr(openwrt.config, "MANAGEMENT_VLAN_DEVICE", "")
    update = parse_config_body(
        {"managementVlan": {"managementVlanEnable": "on", "managementVlanId": 99}}
    )
    runner = RecordingRunner()

    result = OpenWrtUciAdapter(runner).reconcile(
        update,
        _caps(supports_management_vlan=True),
    )

    assert result.applied is False
    assert "OMADA_MANAGEMENT_VLAN_INTERFACE" in result.error
    assert runner.calls == []


def test_reconcile_rejects_portal_free_policy_when_capability_is_disabled():
    update = parse_config_body(
        {"portalFreePolicyConfig": {"portalFreePolicy": [{"value": "192.0.2.10"}]}}
    )
    runner = RecordingRunner()

    result = OpenWrtUciAdapter(runner).reconcile(update, _caps(supports_portal=False))

    assert result.applied is False
    assert "portal free policy requested" in result.error
    assert runner.calls == []


def test_reconcile_allows_portal_wlan_when_capability_is_enabled():
    update = parse_config_body(
        {"ssid_2G": {"radioId": 0, "ssid": [{"ssidName": "guest", "portal": True}]}}
    )
    runner = RecordingRunner()

    result = OpenWrtUciAdapter(runner).reconcile(update, _caps(supports_portal=True))

    assert result.applied is True
    assert result.changed is True
    assert runner.calls[0][0] == ("uci", "-q", "batch")
    assert "set wireless.openomada_2g_guest.ssid='guest'" in (runner.calls[0][1] or "")


def test_reconcile_rejects_wpa3_psk_when_capability_is_disabled():
    update = parse_config_body(
        {
            "ssid_2G": {
                "radioId": 0,
                "ssid": [{"ssidName": "lab", "pskVer": 3, "pskKey": "secret"}],
            }
        }
    )
    runner = RecordingRunner()

    result = OpenWrtUciAdapter(runner).reconcile(update, _caps(supports_wpa3_psk=False))

    assert result.applied is False
    assert "WPA3-PSK WLAN requested" in result.error
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
