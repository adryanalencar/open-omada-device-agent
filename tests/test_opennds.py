import json
from dataclasses import dataclass

from open_omada_device_agent.adapters.outbound.openwrt.opennds import (
    OpenNdsPortalAdapter,
    build_openomada_redirect_themespec,
    opennds_portal_policy_from_omada_config,
    opennds_portal_policy_from_free_policy,
    collect_opennds_clients,
    opennds_clients_from_json,
)
from open_omada_device_agent.contexts.clients.domain import ClientPortalState
from open_omada_device_agent.contexts.portal.domain import (
    PortalConfiguration,
    PortalFreePolicy,
)
from open_omada_device_agent.openwrt import CommandResult
from open_omada_device_agent.platform_capabilities import PlatformCapabilities


@dataclass
class StaticRunner:
    result: CommandResult
    calls: list[tuple[tuple[str, ...], str | None]]

    def run(self, args, *, input_text=None):
        self.calls.append((tuple(args), input_text))
        return self.result


def test_maps_opennds_json_clients_to_portal_overlay_state():
    clients = opennds_clients_from_json(
        {
            "clients": {
                "AA-BB-CC-DD-EE-FF": {
                    "ip": "192.0.2.10",
                    "state": "Authenticated",
                    "download_this_session": "1234",
                    "upload_this_session": "567",
                },
                "02:00:00:00:00:02": {
                    "state": "Preauthenticated",
                },
            }
        }
    )

    assert clients[0].mac == "02:00:00:00:00:02"
    assert clients[0].portal_state is ClientPortalState.UNAUTHENTICATED
    assert clients[1].mac == "aa:bb:cc:dd:ee:ff"
    assert clients[1].ipv4 == "192.0.2.10"
    assert clients[1].portal_state is ClientPortalState.AUTHENTICATED
    assert clients[1].rx_bytes == 1234
    assert clients[1].tx_bytes == 567


def test_collect_opennds_clients_uses_ndsctl_json_when_available():
    runner = StaticRunner(
        result=CommandResult(
            returncode=0,
            stdout=json.dumps(
                {"clients": {"aa:bb:cc:dd:ee:ff": {"state": "Blocked"}}}
            ),
        ),
        calls=[],
    )
    caps = PlatformCapabilities(platform="openwrt", has_opennds=True)

    clients = collect_opennds_clients(capabilities=caps, runner=runner)

    assert clients[0].portal_state is ClientPortalState.BLOCKED
    assert runner.calls == [(("ndsctl", "json"), None)]


def test_collect_opennds_clients_noops_without_opennds():
    runner = StaticRunner(result=CommandResult(returncode=0, stdout="{}"), calls=[])
    caps = PlatformCapabilities(platform="openwrt", has_opennds=False)

    assert collect_opennds_clients(capabilities=caps, runner=runner) == ()
    assert runner.calls == []


def test_builds_opennds_policy_from_portal_free_policy():
    policy = opennds_portal_policy_from_free_policy(
        PortalFreePolicy(
            layer2_rules=(
                {"dstIp": "8.8.8.8", "dstMask": 32},
                {"value": "192.0.2.0", "mask": 24},
            ),
            url_rules=(
                {"url": "mediabeach.com.br/portal/c00e9a43"},
                {"url": "https://privacy.tp-link.com/path"},
                {"url": "mediabeach.com.br"},
            ),
        )
    )

    assert policy.walled_garden_fqdns == ("mediabeach.com.br", "privacy.tp-link.com")
    assert policy.preauthenticated_user_rules == (
        "allow all to 8.8.8.8/32",
        "allow all to 192.0.2.0/24",
    )


def test_builds_opennds_policy_with_controller_portal_redirect():
    policy = opennds_portal_policy_from_omada_config(
        free_policy=PortalFreePolicy(
            url_rules=(
                {"url": "mediabeach.com.br"},
                {"url": "mediabeach.com.br/portal/c00e9a43"},
            ),
        ),
        portal_configs=(
            PortalConfiguration(
                external_portal_server="https://portal.example.com/login",
                redirect_url="https://example.com/after-login",
            ),
        ),
        controller_host="192.0.2.1",
    )

    assert policy.walled_garden_fqdns == ("mediabeach.com.br",)
    assert policy.portal_redirect_url == "https://portal.example.com/login"


def test_builds_opennds_policy_with_portal_url_from_free_policy():
    policy = opennds_portal_policy_from_omada_config(
        free_policy=PortalFreePolicy(
            url_rules=(
                {"url": "mediabeach.com.br"},
                {"url": "mediabeach.com.br/portal/c00e9a43"},
            ),
        ),
        portal_configs=(),
        controller_host="192.0.2.1",
    )

    assert policy.portal_redirect_url == "https://mediabeach.com.br/portal/c00e9a43"


def test_builds_opennds_policy_with_controller_entry_fallback():
    policy = opennds_portal_policy_from_omada_config(
        free_policy=None,
        portal_configs=(),
        controller_host="omada.example.net",
    )

    assert policy.portal_redirect_url == "http://omada.example.net:8088/portal/entry"


def test_builds_openomada_redirect_themespec_without_client_identifiers():
    script = build_openomada_redirect_themespec(
        opennds_portal_policy_from_omada_config(
            free_policy=PortalFreePolicy(
                url_rules=({"url": "mediabeach.com.br/portal/c00e9a43?x=1&y=2"},)
            ),
            controller_host="",
        )
    )

    assert (
        "openomada_portal_url='https://mediabeach.com.br/portal/c00e9a43?x=1&y=2'"
        in script
    )
    assert "clientMac" not in script
    assert "clientIp" not in script
    assert "originurl" not in script
    assert "meta http-equiv" in script


def test_opennds_portal_adapter_applies_walled_garden_to_uci():
    runner = StaticRunner(result=CommandResult(returncode=0), calls=[])
    policy = opennds_portal_policy_from_free_policy(
        PortalFreePolicy(
            layer2_rules=({"dstIp": "8.8.8.8", "dstMask": 32},),
            url_rules=({"url": "mediabeach.com.br/portal/c00e9a43"},),
        )
    )

    result = OpenNdsPortalAdapter(runner).apply(policy)

    assert result.applied is True
    assert result.changed is True
    assert (
        ("uci", "-q", "delete", "opennds.@opennds[0].walledgarden_fqdn_list"),
        None,
    ) in runner.calls
    assert (
        (
            "uci",
            "add_list",
            "opennds.@opennds[0].walledgarden_fqdn_list=mediabeach.com.br",
        ),
        None,
    ) in runner.calls
    assert (
        (
            "uci",
            "add_list",
            "opennds.@opennds[0].walledgarden_port_list=80 443 8088 8843",
        ),
        None,
    ) in runner.calls
    assert (
        (
            "uci",
            "add_list",
            "opennds.@opennds[0].preauthenticated_users=allow all to 8.8.8.8/32",
        ),
        None,
    ) in runner.calls
    assert (("uci", "commit", "opennds"), None) in runner.calls
    assert (("/etc/init.d/opennds", "restart"), None) in runner.calls


def test_opennds_portal_adapter_enables_themespec_redirect():
    runner = StaticRunner(result=CommandResult(returncode=0), calls=[])
    policy = opennds_portal_policy_from_omada_config(
        free_policy=PortalFreePolicy(
            url_rules=({"url": "mediabeach.com.br/portal/c00e9a43"},)
        ),
        controller_host="",
    )

    result = OpenNdsPortalAdapter(runner).apply(policy)

    assert result.applied is True
    assert (
        ("tee", "/usr/lib/opennds/theme_openomada_redirect.sh"),
        build_openomada_redirect_themespec(policy),
    ) in runner.calls
    assert (
        ("chmod", "0644", "/usr/lib/opennds/theme_openomada_redirect.sh"),
        None,
    ) in runner.calls
    assert (
        ("uci", "set", "opennds.@opennds[0].login_option_enabled=3"),
        None,
    ) in runner.calls
    assert (
        (
            "uci",
            "set",
            "opennds.@opennds[0].themespec_path=/usr/lib/opennds/theme_openomada_redirect.sh",
        ),
        None,
    ) in runner.calls


@dataclass
class DeleteMissingRunner:
    calls: list[tuple[str, ...]]

    def run(self, args, *, input_text=None):
        assert input_text is None
        command = tuple(args)
        self.calls.append(command)
        if command[:3] == ("uci", "-q", "delete"):
            return CommandResult(returncode=1)
        return CommandResult(returncode=0)


def test_opennds_portal_adapter_ignores_missing_uci_lists_on_delete():
    runner = DeleteMissingRunner(calls=[])

    result = OpenNdsPortalAdapter(runner).apply(
        opennds_portal_policy_from_free_policy(
            PortalFreePolicy(url_rules=({"url": "mediabeach.com.br"},))
        )
    )

    assert result.applied is True
    assert ("uci", "commit", "opennds") in runner.calls
