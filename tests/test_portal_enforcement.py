from dataclasses import dataclass, field

from open_omada_device_agent.domain import PortalClientState
from open_omada_device_agent.openwrt import CommandResult
from open_omada_device_agent.portal import PortalSession
from open_omada_device_agent.portal_enforcement import (
    NftablesPortalAdapter,
    PortalPolicy,
    build_nftables_rules,
)


@dataclass
class RecordingRunner:
    calls: list[tuple[tuple[str, ...], str | None]] = field(default_factory=list)
    table_exists: bool = True

    def run(self, args, *, input_text=None):
        command = tuple(args)
        self.calls.append((command, input_text))
        if command == ("nft", "list", "table", "inet", "openomada_portal"):
            return CommandResult(returncode=0 if self.table_exists else 1)
        return CommandResult(returncode=0)


def test_build_nftables_rules_for_authenticated_and_blocked_clients():
    rules = build_nftables_rules(
        PortalPolicy(
            interface="br-guest",
            redirect_port=8080,
            walled_garden_ipv4=("192.0.2.10",),
        ),
        (
            PortalSession(mac="aa:bb:cc:dd:ee:ff", state=PortalClientState.AUTHENTICATED),
            PortalSession(mac="02:00:00:00:00:02", state=PortalClientState.BLOCKED),
        ),
    )

    assert "table inet openomada_portal" in rules
    assert "aa:bb:cc:dd:ee:ff" in rules
    assert "02:00:00:00:00:02" in rules
    assert "udp dport { 53, 67, 68 } accept" in rules
    assert "ip daddr @walled_garden_v4 accept" in rules
    assert "tcp dport 80 redirect to :8080" in rules
    assert "tcp dport 443 drop" in rules


def test_nftables_adapter_replaces_existing_table_without_shell():
    runner = RecordingRunner(table_exists=True)
    adapter = NftablesPortalAdapter(runner)

    result = adapter.apply(
        PortalPolicy(interface="br-guest", redirect_port=8080),
        (),
    )

    assert result.applied is True
    assert runner.calls[0][0] == ("nft", "list", "table", "inet", "openomada_portal")
    assert runner.calls[1][0] == ("nft", "delete", "table", "inet", "openomada_portal")
    assert runner.calls[2][0] == ("nft", "-f", "-")
    assert runner.calls[2][1] is not None
    assert "elements = {  }" not in runner.calls[2][1]


def test_nftables_adapter_rejects_invalid_interface():
    runner = RecordingRunner()
    adapter = NftablesPortalAdapter(runner)

    result = adapter.apply(
        PortalPolicy(interface="guest; rm -rf /", redirect_port=8080),
        (),
    )

    assert result.applied is False
    assert "invalid portal interface" in result.error
    assert runner.calls == []
