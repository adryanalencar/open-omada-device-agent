import json
import subprocess
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
                site_name="HQ",
                ssid_list=("lab-wlan",),
            ),
        ),
        controller_host="192.0.2.1",
        device_mac="02-11-22-33-44-55",
    )

    assert policy.walled_garden_fqdns == ("mediabeach.com.br",)
    assert policy.portal_redirect_url == "https://portal.example.com/login"
    assert policy.landing_page_url == "https://example.com/after-login"
    assert policy.default_ssid_name == "lab-wlan"
    assert policy.ap_mac == "02:11:22:33:44:55"
    assert policy.site_name == "HQ"


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
        site_name="Pereque Mirim",
    )

    assert policy.portal_redirect_url == "https://mediabeach.com.br/portal/c00e9a43"
    assert policy.site_name == "Pereque Mirim"


def test_builds_opennds_policy_with_controller_entry_fallback():
    policy = opennds_portal_policy_from_omada_config(
        free_policy=None,
        portal_configs=(),
        controller_host="omada.example.net",
    )

    assert policy.portal_redirect_url == "http://omada.example.net:8088/portal/entry"


def test_builds_openomada_redirect_themespec_with_omada_eap_parameters():
    policy = opennds_portal_policy_from_omada_config(
        free_policy=PortalFreePolicy(
            url_rules=({"url": "mediabeach.com.br/portal/c00e9a43?x=1&y=2"},)
        ),
        portal_configs=(
            PortalConfiguration(
                redirect_url="https://example.com/after-login",
                site_id="ffff16a3ab739b57bd5247ec2ff8b",
                site_name="Pereque Mirim",
                ssid_list=("Ubatuba - Wifi Grátis",),
            ),
        ),
        controller_host="",
        device_mac="02:11:22:33:44:55",
        site_id="ffff16a3ab739b57bd5247ec2ff8b",
    )
    script = build_openomada_redirect_themespec(policy)

    assert (
        "openomada_portal_url='https://mediabeach.com.br/portal/c00e9a43?x=1&y=2'"
        in script
    )
    assert "clientMac" in script
    assert "apMac" in script
    assert "ssidName" in script
    assert "radioId" in script
    assert "site" in script
    assert "redirectUrl" in script
    assert "clientIp" in script
    assert "originurl" in script
    assert "meta http-equiv" in script


def test_openomada_redirect_themespec_emits_tp_link_external_portal_url():
    policy = opennds_portal_policy_from_omada_config(
        free_policy=PortalFreePolicy(
            url_rules=({"url": "mediabeach.com.br/portal/c00e9a43?x=1&y=2"},)
        ),
        portal_configs=(
            PortalConfiguration(
                redirect_url="https://example.com/after-login",
                site_id="ffff16a3ab739b57bd5247ec2ff8b",
                site_name="Pereque Mirim",
                ssid_list=("Ubatuba - Wifi Grátis",),
            ),
        ),
        controller_host="",
        device_mac="02:11:22:33:44:55",
        site_id="ffff16a3ab739b57bd5247ec2ff8b",
    )
    script = "\n".join(
        (
            build_openomada_redirect_themespec(policy),
            "clientmac='aa:bb:cc:dd:ee:ff'",
            "clientip='192.168.1.123'",
            "clientif=''",
            "originurl='http%3A%2F%2Forigin.example%2Fpath'",
            "date() { printf '%s\\n' '1787784794'; }",
            "generate_splash_sequence",
        )
    )

    result = subprocess.run(
        ["/bin/sh"],
        input=script,
        text=True,
        check=True,
        capture_output=True,
    )

    assert "https://mediabeach.com.br/portal/c00e9a43?x=1&amp;y=2" in result.stdout
    assert "clientMac=AA-BB-CC-DD-EE-FF" in result.stdout
    assert "clientIp=192.168.1.123" in result.stdout
    assert "t=1787784794" in result.stdout
    assert "site=ffff16a3ab739b57bd5247ec2ff8b" in result.stdout
    assert "apMac=02-11-22-33-44-55" in result.stdout
    assert "ssidName=Ubatuba+-+Wifi+Gr%C3%A1tis" in result.stdout
    assert "radioId=0" in result.stdout
    assert "redirectUrl=https%3A%2F%2Fexample.com%2Fafter-login" in result.stdout


def test_openomada_redirect_themespec_decodes_iw_hex_escaped_ssid():
    policy = opennds_portal_policy_from_omada_config(
        free_policy=PortalFreePolicy(
            url_rules=({"url": "mediabeach.com.br/portal/c00e9a43"},)
        ),
        portal_configs=(PortalConfiguration(site_name="Pereque Mirim"),),
        controller_host="",
        device_mac="02:11:22:33:44:55",
    )
    script = "\n".join(
        (
            build_openomada_redirect_themespec(policy),
            "iw() {",
            "    printf '%s\\n' 'Interface phy0-ap0'",
            "    printf '%s\\n' '        ssid Ubatuba - Wifi Gr\\xc3\\xa1tis'",
            "    printf '%s\\n' '        channel 6 (2437 MHz), width: 20 MHz'",
            "}",
            "clientmac='aa:bb:cc:dd:ee:ff'",
            "clientif='phy0-ap0'",
            "generate_splash_sequence",
        )
    )

    result = subprocess.run(
        ["/bin/sh"],
        input=script,
        text=True,
        check=True,
        capture_output=True,
    )

    assert "ssidName=Ubatuba+-+Wifi+Gr%C3%A1tis" in result.stdout


def test_openomada_redirect_themespec_decodes_opennds_html_escaped_origin_url():
    policy = opennds_portal_policy_from_omada_config(
        free_policy=PortalFreePolicy(
            url_rules=({"url": "mediabeach.com.br/portal/c00e9a43"},)
        ),
        portal_configs=(PortalConfiguration(site_id="ffff16a3ab739b57bd5247ec2ff8b"),),
        controller_host="",
        device_mac="02:11:22:33:44:55",
    )
    script = "\n".join(
        (
            build_openomada_redirect_themespec(policy),
            "clientmac='aa:bb:cc:dd:ee:ff'",
            "clientip='192.168.1.123'",
            "clientif=''",
            "originurl='http:&#47;&#47;connectivitycheck.gstatic.com&#47;generate_204'",
            "generate_splash_sequence",
        )
    )

    result = subprocess.run(
        ["/bin/sh"],
        input=script,
        text=True,
        check=True,
        capture_output=True,
    )

    assert (
        "redirectUrl=http%3A%2F%2Fconnectivitycheck.gstatic.com%2Fgenerate_204"
        in result.stdout
    )


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
    assert (
        ("uci", "set", "opennds.@opennds[0].allow_preemptive_authentication=0"),
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
