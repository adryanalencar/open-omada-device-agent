"""OpenWrt startup bootstrap for AP runtime prerequisites."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from ....application.contracts import PlatformCapabilities
from .uci import CommandRunner, SubprocessRunner


log = logging.getLogger("open_omada.openwrt.bootstrap")


@dataclass(frozen=True)
class OpenWrtBootstrapConfig:
    enabled: bool = True
    ensure_lan: bool = True
    lan_interface: str = "lan"
    lan_bridge: str = "br-lan"
    lan_ipaddr: str = "192.168.1.1/24"
    ensure_opennds: bool = True
    opennds_gateway_port: int = 2050
    opennds_gateway_name: str = "OpenOmada-AP"
    enable_wan_management: bool = False
    wan_zone: str = "wan"


@dataclass(frozen=True)
class OpenWrtBootstrapResult:
    applied: bool
    changed: bool = False
    warnings: tuple[str, ...] = ()
    command_count: int = 0


class OpenWrtStartupBootstrap:
    def __init__(
        self,
        runner: CommandRunner | None = None,
        *,
        config: OpenWrtBootstrapConfig | None = None,
    ) -> None:
        self._runner = runner or SubprocessRunner()
        self._config = config or OpenWrtBootstrapConfig()

    def apply(self, capabilities: PlatformCapabilities) -> OpenWrtBootstrapResult:
        if not self._config.enabled or capabilities.platform != "openwrt":
            return OpenWrtBootstrapResult(applied=True)
        if not capabilities.has_uci:
            return OpenWrtBootstrapResult(
                applied=True,
                warnings=("OpenWrt bootstrap skipped because uci is not available",),
            )

        changed = False
        command_count = 0
        warnings: list[str] = []

        if self._config.ensure_lan:
            result = self._ensure_lan_bridge()
            changed = changed or result.changed
            command_count += result.command_count
            warnings.extend(result.warnings)

        if self._config.enable_wan_management:
            result = self._ensure_wan_management()
            changed = changed or result.changed
            command_count += result.command_count
            warnings.extend(result.warnings)

        if self._config.ensure_opennds and capabilities.has_opennds:
            result = self._ensure_opennds()
            changed = changed or result.changed
            command_count += result.command_count
            warnings.extend(result.warnings)

        for warning in warnings:
            log.warning(warning)
        if changed:
            log.info("OpenWrt startup bootstrap applied %d command(s)", command_count)
        return OpenWrtBootstrapResult(
            applied=True,
            changed=changed,
            warnings=tuple(dict.fromkeys(warnings)),
            command_count=command_count,
        )

    def _ensure_lan_bridge(self) -> OpenWrtBootstrapResult:
        bridge = self._config.lan_bridge
        lan = self._config.lan_interface
        lines: list[str] = []

        bridge_section = self._find_section_by_option("network", "name", bridge)
        if bridge_section is None:
            bridge_section = "openomada_br_lan"
            self._append_section_if_needed(lines, "network", bridge_section, "device")
            self._append_set_if_needed(lines, "network", bridge_section, "name", bridge)
        self._append_set_if_needed(lines, "network", bridge_section, "type", "bridge")
        self._append_set_if_needed(lines, "network", bridge_section, "bridge_empty", "1")

        if self._uci_get(f"network.{lan}") != "interface":
            self._append_section_if_needed(lines, "network", lan, "interface")
        if not self._uci_get(f"network.{lan}.device"):
            self._append_set_if_needed(lines, "network", lan, "device", bridge)
        if not self._uci_get(f"network.{lan}.proto"):
            self._append_set_if_needed(lines, "network", lan, "proto", "static")
        if not self._uci_get(f"network.{lan}.ipaddr"):
            self._append_set_if_needed(lines, "network", lan, "ipaddr", self._config.lan_ipaddr)

        if not lines:
            return OpenWrtBootstrapResult(applied=True)

        result = self._run_batch("network", lines)
        warnings = list(result.warnings)
        command_count = result.command_count
        if not result.changed:
            return result
        for command in (("/etc/init.d/network", "reload"), ("wifi", "reload")):
            run_result = self._runner.run(command)
            command_count += 1
            if run_result.returncode != 0:
                warnings.append(_command_warning(command, run_result))
        return OpenWrtBootstrapResult(
            applied=True,
            changed=True,
            warnings=tuple(warnings),
            command_count=command_count,
        )

    def _ensure_wan_management(self) -> OpenWrtBootstrapResult:
        lines: list[str] = []
        for section, name, port in (
            ("openomada_allow_ssh_wan", "Allow-SSH-WAN", "22"),
            ("openomada_allow_luci_http_wan", "Allow-LuCI-HTTP-WAN", "80"),
            ("openomada_allow_luci_https_wan", "Allow-LuCI-HTTPS-WAN", "443"),
        ):
            self._append_section_if_needed(lines, "firewall", section, "rule")
            self._append_set_if_needed(lines, "firewall", section, "name", name)
            self._append_set_if_needed(lines, "firewall", section, "src", self._config.wan_zone)
            self._append_set_if_needed(lines, "firewall", section, "proto", "tcp")
            self._append_set_if_needed(lines, "firewall", section, "dest_port", port)
            self._append_set_if_needed(lines, "firewall", section, "target", "ACCEPT")

        if not lines:
            return OpenWrtBootstrapResult(applied=True)

        result = self._run_batch("firewall", lines)
        warnings = list(result.warnings)
        command_count = result.command_count
        if not result.changed:
            return result
        run_result = self._runner.run(("/etc/init.d/firewall", "reload"))
        command_count += 1
        if run_result.returncode != 0:
            warnings.append(_command_warning(("/etc/init.d/firewall", "reload"), run_result))
        return OpenWrtBootstrapResult(
            applied=True,
            changed=True,
            warnings=tuple(warnings),
            command_count=command_count,
        )

    def _ensure_opennds(self) -> OpenWrtBootstrapResult:
        lines: list[str] = []
        section = "@opennds[0]"
        if self._uci_get("opennds.@opennds[0]") != "opennds":
            section = "openomada"
            self._append_section_if_needed(lines, "opennds", section, "opennds")

        self._append_set_if_needed(lines, "opennds", section, "enabled", "1")
        self._append_set_if_needed(
            lines,
            "opennds",
            section,
            "gatewayinterface",
            self._config.lan_bridge,
        )
        self._append_set_if_needed(
            lines,
            "opennds",
            section,
            "gatewayport",
            str(self._config.opennds_gateway_port),
        )
        if self._config.opennds_gateway_name:
            self._append_set_if_needed(
                lines,
                "opennds",
                section,
                "gatewayname",
                self._config.opennds_gateway_name,
            )
        self._append_set_if_needed(
            lines,
            "opennds",
            section,
            "allow_preemptive_authentication",
            "0",
        )

        command_count = 0
        warnings: list[str] = []
        changed = bool(lines)
        if lines:
            result = self._run_batch("opennds", lines)
            command_count += result.command_count
            warnings.extend(result.warnings)
            if not result.changed:
                return OpenWrtBootstrapResult(
                    applied=True,
                    warnings=tuple(warnings),
                    command_count=command_count,
                )

        action = "restart" if changed else "start"
        command = ("/etc/init.d/opennds", action)
        run_result = self._runner.run(command)
        command_count += 1
        if run_result.returncode != 0:
            warnings.append(_command_warning(command, run_result))
        return OpenWrtBootstrapResult(
            applied=True,
            changed=changed,
            warnings=tuple(warnings),
            command_count=command_count,
        )

    def _run_batch(self, config: str, lines: list[str]) -> OpenWrtBootstrapResult:
        payload = "\n".join((*lines, f"commit {config}")) + "\n"
        result = self._runner.run(("uci", "-q", "batch"), input_text=payload)
        if result.returncode != 0:
            return OpenWrtBootstrapResult(
                applied=True,
                warnings=(_command_warning(("uci", "-q", "batch"), result),),
                command_count=1,
            )
        return OpenWrtBootstrapResult(applied=True, changed=True, command_count=1)

    def _append_section_if_needed(
        self,
        lines: list[str],
        config: str,
        section: str,
        section_type: str,
    ) -> None:
        if self._uci_get(f"{config}.{section}") == section_type:
            return
        lines.append(f"set {config}.{section}={section_type}")

    def _append_set_if_needed(
        self,
        lines: list[str],
        config: str,
        section: str,
        option: str,
        value: str,
    ) -> None:
        if self._uci_get(f"{config}.{section}.{option}") == value:
            return
        lines.append(f"set {config}.{section}.{option}='{_uci_quote(value)}'")

    def _uci_get(self, path: str) -> str:
        result = self._runner.run(("uci", "-q", "get", path))
        if result.returncode != 0:
            return ""
        return result.stdout.strip()

    def _find_section_by_option(self, config: str, option: str, value: str) -> str | None:
        result = self._runner.run(("uci", "-q", "show", config))
        if result.returncode != 0:
            return None
        suffix = f".{option}='{value}'"
        for line in result.stdout.splitlines():
            if not line.startswith(f"{config}.") or not line.endswith(suffix):
                continue
            return line[len(config) + 1 : -len(suffix)]
        return None


def _uci_quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "'\\''")


def _command_warning(command: tuple[str, ...], result) -> str:
    output = (result.stderr or result.stdout or "").strip()
    if output:
        return f"{' '.join(command)} failed: {output}"
    return f"{' '.join(command)} failed with exit code {result.returncode}"
