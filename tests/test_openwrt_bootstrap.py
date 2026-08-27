from dataclasses import dataclass, field

from open_omada_device_agent.adapters.outbound.openwrt.bootstrap import (
    OpenWrtBootstrapConfig,
    OpenWrtStartupBootstrap,
)
from open_omada_device_agent.openwrt import CommandResult
from open_omada_device_agent.platform_capabilities import PlatformCapabilities


@dataclass
class BootstrapRunner:
    responses: dict[tuple[str, ...], CommandResult] = field(default_factory=dict)
    calls: list[tuple[tuple[str, ...], str | None]] = field(default_factory=list)

    def run(self, args, *, input_text=None):
        command = tuple(args)
        self.calls.append((command, input_text))
        if command in self.responses:
            return self.responses[command]
        if command[:3] == ("uci", "-q", "get"):
            return CommandResult(returncode=1)
        if command[:3] == ("uci", "-q", "show"):
            return CommandResult(returncode=1)
        return CommandResult(returncode=0)


def _caps(**overrides):
    values = {
        "platform": "openwrt",
        "has_uci": True,
        "has_opennds": False,
    }
    values.update(overrides)
    return PlatformCapabilities(**values)


def _batch_payloads(runner: BootstrapRunner) -> list[str]:
    return [
        input_text or ""
        for command, input_text in runner.calls
        if command == ("uci", "-q", "batch")
    ]


def test_bootstrap_enables_empty_br_lan_and_reloads_network():
    runner = BootstrapRunner(
        responses={
            ("uci", "-q", "show", "network"): CommandResult(
                returncode=0,
                stdout="network.@device[0]=device\nnetwork.@device[0].name='br-lan'\n",
            ),
            ("uci", "-q", "get", "network.@device[0].type"): CommandResult(
                returncode=0,
                stdout="bridge\n",
            ),
            ("uci", "-q", "get", "network.lan"): CommandResult(
                returncode=0,
                stdout="interface\n",
            ),
            ("uci", "-q", "get", "network.lan.device"): CommandResult(
                returncode=0,
                stdout="br-lan\n",
            ),
            ("uci", "-q", "get", "network.lan.proto"): CommandResult(
                returncode=0,
                stdout="static\n",
            ),
            ("uci", "-q", "get", "network.lan.ipaddr"): CommandResult(
                returncode=0,
                stdout="192.168.1.1/24\n",
            ),
        }
    )

    result = OpenWrtStartupBootstrap(runner).apply(_caps())

    assert result.changed is True
    batch = _batch_payloads(runner)[0]
    assert "set network.@device[0].bridge_empty='1'" in batch
    assert "commit network" in batch
    assert (("/etc/init.d/network", "reload"), None) in runner.calls
    assert (("wifi", "reload"), None) in runner.calls


def test_bootstrap_creates_minimal_lan_bridge_when_missing():
    runner = BootstrapRunner(
        responses={
            ("uci", "-q", "show", "network"): CommandResult(returncode=0, stdout=""),
        }
    )

    OpenWrtStartupBootstrap(runner).apply(_caps())

    batch = _batch_payloads(runner)[0]
    assert "set network.openomada_br_lan=device" in batch
    assert "set network.openomada_br_lan.name='br-lan'" in batch
    assert "set network.openomada_br_lan.type='bridge'" in batch
    assert "set network.openomada_br_lan.bridge_empty='1'" in batch
    assert "set network.lan=interface" in batch
    assert "set network.lan.device='br-lan'" in batch
    assert "set network.lan.proto='static'" in batch
    assert "set network.lan.ipaddr='192.168.1.1/24'" in batch


def test_bootstrap_configures_opennds_base_and_disables_preemptive_auth():
    runner = BootstrapRunner(
        responses={
            ("uci", "-q", "get", "opennds.@opennds[0]"): CommandResult(
                returncode=0,
                stdout="opennds\n",
            ),
            ("uci", "-q", "get", "opennds.@opennds[0].gatewayport"): CommandResult(
                returncode=0,
                stdout="2050\n",
            ),
            ("uci", "-q", "get", "opennds.@opennds[0].gatewayfqdn"): CommandResult(
                returncode=0,
                stdout="status.client\n",
            ),
        }
    )
    bootstrap = OpenWrtStartupBootstrap(
        runner,
        config=OpenWrtBootstrapConfig(
            ensure_lan=False,
            opennds_gateway_name="OpenOmada Ubatuba",
        ),
    )

    result = bootstrap.apply(_caps(has_opennds=True))

    assert result.changed is True
    batch = _batch_payloads(runner)[0]
    assert "set opennds.@opennds[0].enabled='1'" in batch
    assert "set opennds.@opennds[0].gatewayinterface='br-lan'" in batch
    assert "set opennds.@opennds[0].gatewayname='OpenOmada Ubatuba'" in batch
    assert "set opennds.@opennds[0].gatewayfqdn='disable'" in batch
    assert "set opennds.@opennds[0].allow_preemptive_authentication='0'" in batch
    assert (("/etc/init.d/opennds", "restart"), None) in runner.calls


def test_bootstrap_starts_opennds_when_base_config_is_already_current():
    runner = BootstrapRunner(
        responses={
            ("uci", "-q", "get", "opennds.@opennds[0]"): CommandResult(
                returncode=0,
                stdout="opennds\n",
            ),
            ("uci", "-q", "get", "opennds.@opennds[0].enabled"): CommandResult(
                returncode=0,
                stdout="1\n",
            ),
            ("uci", "-q", "get", "opennds.@opennds[0].gatewayinterface"): CommandResult(
                returncode=0,
                stdout="br-lan\n",
            ),
            ("uci", "-q", "get", "opennds.@opennds[0].gatewayport"): CommandResult(
                returncode=0,
                stdout="2050\n",
            ),
            ("uci", "-q", "get", "opennds.@opennds[0].gatewayname"): CommandResult(
                returncode=0,
                stdout="OpenOmada-AP\n",
            ),
            ("uci", "-q", "get", "opennds.@opennds[0].gatewayfqdn"): CommandResult(
                returncode=0,
                stdout="disable\n",
            ),
            (
                "uci",
                "-q",
                "get",
                "opennds.@opennds[0].allow_preemptive_authentication",
            ): CommandResult(returncode=0, stdout="0\n"),
        }
    )
    bootstrap = OpenWrtStartupBootstrap(
        runner,
        config=OpenWrtBootstrapConfig(ensure_lan=False),
    )

    result = bootstrap.apply(_caps(has_opennds=True))

    assert result.changed is False
    assert _batch_payloads(runner) == []
    assert (("/etc/init.d/opennds", "start"), None) in runner.calls


def test_bootstrap_adds_wan_management_rules_only_when_enabled():
    runner = BootstrapRunner()
    bootstrap = OpenWrtStartupBootstrap(
        runner,
        config=OpenWrtBootstrapConfig(
            ensure_lan=False,
            ensure_opennds=False,
            enable_wan_management=True,
        ),
    )

    result = bootstrap.apply(_caps())

    assert result.changed is True
    batch = _batch_payloads(runner)[0]
    assert "set firewall.openomada_allow_ssh_wan=rule" in batch
    assert "set firewall.openomada_allow_ssh_wan.dest_port='22'" in batch
    assert "set firewall.openomada_allow_luci_http_wan.dest_port='80'" in batch
    assert "set firewall.openomada_allow_luci_https_wan.dest_port='443'" in batch
    assert (("/etc/init.d/firewall", "reload"), None) in runner.calls


def test_bootstrap_noops_outside_openwrt():
    runner = BootstrapRunner()

    result = OpenWrtStartupBootstrap(runner).apply(PlatformCapabilities(platform="generic"))

    assert result.changed is False
    assert runner.calls == []
