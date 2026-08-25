"""Local device command adapters for AP SET_REQUEST command-like keys."""
from __future__ import annotations

import json
import ipaddress
import re
from dataclasses import dataclass
from pathlib import Path

from .... import config
from ....application.commands import ApplyDeviceConfigurationCommand
from ....contexts.clients.domain import ClientOperationCode, ClientRateConfig
from ....shared.domain import MacAddress
from .uci import CommandRunner, SubprocessRunner
from ....application.contracts import PlatformCapabilities

NFT_CLIENT_TABLE = "openomada_clients"
NFT_CLIENT_RATE_TABLE = "openomada_client_rates"


@dataclass(frozen=True)
class DeviceCommandResult:
    applied: bool
    changed: bool = False
    error: str = ""


class SysfsLedAdapter:
    def __init__(
        self,
        *,
        brightness_path: str | None = None,
        trigger_path: str | None = None,
        on_value: str | None = None,
        off_value: str | None = None,
        locate_trigger: str | None = None,
        default_trigger: str | None = None,
    ) -> None:
        self._brightness_path = brightness_path if brightness_path is not None else config.LED_BRIGHTNESS_PATH
        self._trigger_path = trigger_path if trigger_path is not None else config.LED_TRIGGER_PATH
        self._on_value = config.LED_ON_VALUE if on_value is None else on_value
        self._off_value = config.LED_OFF_VALUE if off_value is None else off_value
        self._locate_trigger = (
            config.LED_LOCATE_TRIGGER if locate_trigger is None else locate_trigger
        )
        self._default_trigger = (
            config.LED_DEFAULT_TRIGGER if default_trigger is None else default_trigger
        )

    def validate_update(
        self,
        update: ApplyDeviceConfigurationCommand,
        capabilities: PlatformCapabilities,
    ) -> tuple[str, ...]:
        errors = []
        if update.wifi_control_led is not None:
            errors.append("WiFi control LED reconciliation is not implemented")
        if update.led is None:
            return tuple(errors)
        if (
            (update.led.enabled is not None or update.led.locate is not None)
            and not capabilities.supports_led_control
        ):
            errors.append("LED control requested but platform capability is disabled")
        if update.led.enabled is not None and not self._brightness_path:
            errors.append("LED brightness path is not configured")
        if update.led.locate is not None and not self._trigger_path:
            errors.append("LED trigger path is not configured")
        return tuple(dict.fromkeys(errors))

    def reconcile(
        self,
        update: ApplyDeviceConfigurationCommand,
        capabilities: PlatformCapabilities,
    ) -> DeviceCommandResult:
        errors = self.validate_update(update, capabilities)
        if errors:
            return DeviceCommandResult(applied=False, error="; ".join(errors))
        if update.led is None:
            return DeviceCommandResult(applied=True, changed=False)
        changed = False
        if update.led.enabled is not None:
            value = self._on_value if update.led.enabled else self._off_value
            try:
                Path(self._brightness_path).write_text(str(value) + "\n", encoding="ascii")
            except OSError as exc:
                return DeviceCommandResult(
                    applied=False,
                    error=f"LED brightness write failed: {exc}",
                )
            changed = True
        if update.led.locate is not None:
            value = self._locate_trigger if update.led.locate else self._default_trigger
            try:
                Path(self._trigger_path).write_text(str(value) + "\n", encoding="ascii")
            except OSError as exc:
                return DeviceCommandResult(
                    applied=False,
                    error=f"LED trigger write failed: {exc}",
                )
            changed = True
        return DeviceCommandResult(applied=True, changed=changed)


class OpenWrtClientControlAdapter:
    def __init__(
        self,
        runner: CommandRunner | None = None,
        *,
        hostapd_iface: str | None = None,
        block_interface: str | None = None,
        rate_limit_interface: str | None = None,
    ) -> None:
        self._runner = runner or SubprocessRunner()
        self._hostapd_iface = (
            config.HOSTAPD_UBUS_IFACE if hostapd_iface is None else hostapd_iface
        )
        self._block_interface = (
            config.CLIENT_BLOCK_INTERFACE if block_interface is None else block_interface
        )
        self._rate_limit_interface = (
            config.CLIENT_RATE_LIMIT_INTERFACE
            if rate_limit_interface is None
            else rate_limit_interface
        )

    def validate_update(
        self,
        update: ApplyDeviceConfigurationCommand,
        capabilities: PlatformCapabilities,
    ) -> tuple[str, ...]:
        errors: list[str] = []
        if update.client_configs:
            if not capabilities.has_opennds:
                errors.append("clientConfig unauth reconciliation requires openNDS")
            for item in update.client_configs:
                try:
                    MacAddress(item.client_mac)
                except ValueError:
                    errors.append(f"invalid clientConfig MAC: {item.client_mac!r}")
        if update.client_rate_config is not None:
            if not capabilities.supports_client_rate_limits:
                errors.append("client rate-limit requested but platform capability is disabled")
            if not capabilities.has_nft:
                errors.append("client rate-limit requires nft")
            if not self._rate_limit_interface:
                errors.append("OMADA_CLIENT_RATE_LIMIT_INTERFACE is required")
            elif not _valid_interface(self._rate_limit_interface):
                errors.append(f"invalid client rate-limit interface: {self._rate_limit_interface!r}")
            for limit in update.client_rate_config.limits:
                try:
                    MacAddress(limit.mac)
                except ValueError:
                    errors.append(f"invalid client rate-limit MAC: {limit.mac!r}")
                if limit.down is not None and limit.down < 0:
                    errors.append(f"negative client down rate-limit for {limit.mac}")
                if limit.up is not None and limit.up < 0:
                    errors.append(f"negative client up rate-limit for {limit.mac}")
        if not update.client_operations:
            return tuple(errors)
        if not capabilities.supports_client_operations:
            errors.append("client operations requested but platform capability is disabled")

        needs_hostapd = False
        needs_nft = False
        for operation in update.client_operations:
            code = operation.operation_code
            try:
                MacAddress(operation.client_mac)
            except ValueError:
                errors.append(f"invalid client MAC: {operation.client_mac!r}")
            if operation.wireless is False:
                errors.append("wired client operations are not implemented")
            if code is None:
                errors.append(
                    f"unknown client operation {operation.operation!r} for {operation.client_mac}"
                )
                continue
            if code in {
                ClientOperationCode.RECONNECT,
                ClientOperationCode.PORTAL_UNAUTH,
            }:
                needs_hostapd = True
            elif code in {
                ClientOperationCode.BLOCK,
                ClientOperationCode.UNBLOCK,
            }:
                needs_nft = True
            else:
                errors.append(
                    f"client operation {code.name} ({int(code)}) is not implemented"
                )

        if needs_hostapd and not capabilities.has_ubus:
            errors.append("client reconnect requires ubus")
        if needs_hostapd and not self._hostapd_iface:
            errors.append("OMADA_HOSTAPD_UBUS_IFACE is required for client reconnect")
        if needs_hostapd and self._hostapd_iface and not _valid_object_suffix(self._hostapd_iface):
            errors.append(f"invalid hostapd ubus interface: {self._hostapd_iface!r}")
        if needs_nft and not capabilities.has_nft:
            errors.append("client block/unblock requires nft")
        if needs_nft and not self._block_interface:
            errors.append("OMADA_CLIENT_BLOCK_INTERFACE is required for client block/unblock")
        if needs_nft and self._block_interface and not _valid_interface(self._block_interface):
            errors.append(f"invalid client block interface: {self._block_interface!r}")
        return tuple(dict.fromkeys(errors))

    def reconcile(
        self,
        update: ApplyDeviceConfigurationCommand,
        capabilities: PlatformCapabilities,
    ) -> DeviceCommandResult:
        errors = self.validate_update(update, capabilities)
        if errors:
            return DeviceCommandResult(applied=False, error="; ".join(errors))
        if (
            not update.client_configs
            and not update.client_operations
            and update.client_rate_config is None
        ):
            return DeviceCommandResult(applied=True, changed=False)

        changed = False
        for item in update.client_configs:
            if item.unauthenticated is None:
                continue
            mac = MacAddress(item.client_mac).value
            result = (
                self._deauthenticate_portal_client(mac)
                if item.unauthenticated
                else self._authenticate_portal_client(mac)
            )
            if not result.applied:
                return result
            changed = changed or result.changed
        if update.client_rate_config is not None:
            result = self._apply_client_rate_limits(update.client_rate_config)
            if not result.applied:
                return result
            changed = changed or result.changed
        for operation in update.client_operations:
            code = operation.operation_code
            mac = MacAddress(operation.client_mac).value
            if code in {
                ClientOperationCode.RECONNECT,
                ClientOperationCode.PORTAL_UNAUTH,
            }:
                result = self._disconnect_client(mac)
            elif code is ClientOperationCode.BLOCK:
                result = self._set_client_block(mac, blocked=True)
            elif code is ClientOperationCode.UNBLOCK:
                result = self._set_client_block(mac, blocked=False)
            else:
                continue
            if not result.applied:
                return result
            changed = changed or result.changed
        return DeviceCommandResult(applied=True, changed=changed)

    def _apply_client_rate_limits(
        self,
        rate_config: ClientRateConfig,
    ) -> DeviceCommandResult:
        existing = self._runner.run(
            ["nft", "list", "table", "bridge", NFT_CLIENT_RATE_TABLE]
        )
        if existing.returncode == 0:
            deleted = self._runner.run(
                ["nft", "delete", "table", "bridge", NFT_CLIENT_RATE_TABLE]
            )
            if deleted.returncode != 0:
                return DeviceCommandResult(
                    applied=False,
                    error=(
                        deleted.stderr
                        or deleted.stdout
                        or "nft client rate table delete failed"
                    ).strip(),
                )
        loaded = self._runner.run(
            ["nft", "-f", "-"],
            input_text=build_client_rate_limit_nftables_rules(
                self._rate_limit_interface,
                rate_config,
            ),
        )
        if loaded.returncode != 0:
            return DeviceCommandResult(
                applied=False,
                error=(loaded.stderr or loaded.stdout or "nft client rate load failed").strip(),
            )
        return DeviceCommandResult(applied=True, changed=True)

    def _disconnect_client(self, mac: str) -> DeviceCommandResult:
        payload = json.dumps(
            {"addr": mac, "reason": 5, "deauth": True, "ban_time": 0},
            separators=(",", ":"),
        )
        result = self._runner.run(
            ["ubus", "call", f"hostapd.{self._hostapd_iface}", "del_client", payload]
        )
        if result.returncode != 0:
            return DeviceCommandResult(
                applied=False,
                error=(result.stderr or result.stdout or "ubus hostapd del_client failed").strip(),
            )
        return DeviceCommandResult(applied=True, changed=True)

    def _authenticate_portal_client(self, mac: str) -> DeviceCommandResult:
        result = self._runner.run(["ndsctl", "auth", mac, "", "", "", "", "", ""])
        if result.returncode != 0:
            return DeviceCommandResult(
                applied=False,
                error=(result.stderr or result.stdout or "ndsctl auth failed").strip(),
            )
        return DeviceCommandResult(applied=True, changed=True)

    def _deauthenticate_portal_client(self, mac: str) -> DeviceCommandResult:
        client_ip = self._portal_client_ip(mac)
        result = self._runner.run(["ndsctl", "deauth", mac])
        if result.returncode != 0:
            return DeviceCommandResult(
                applied=False,
                error=(result.stderr or result.stdout or "ndsctl deauth failed").strip(),
            )
        if client_ip is not None:
            self._flush_portal_client_conntrack(client_ip)
        return DeviceCommandResult(applied=True, changed=True)

    def _portal_client_ip(self, mac: str) -> str | None:
        result = self._runner.run(["ndsctl", "json", mac])
        if result.returncode != 0 or not result.stdout.strip():
            return None
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        raw_clients = payload.get("clients")
        if not isinstance(raw_clients, dict):
            return None
        raw_client = raw_clients.get(mac)
        if not isinstance(raw_client, dict):
            return None
        raw_ip = raw_client.get("ip")
        if raw_ip is None:
            return None
        try:
            return str(ipaddress.ip_address(str(raw_ip)))
        except ValueError:
            return None

    def _flush_portal_client_conntrack(self, client_ip: str) -> None:
        for direction in ("-s", "-d"):
            self._runner.run(["conntrack", "-D", direction, client_ip])

    def _set_client_block(self, mac: str, *, blocked: bool) -> DeviceCommandResult:
        ensured = self._ensure_client_block_table()
        if not ensured.applied:
            return ensured
        action = "add" if blocked else "delete"
        result = self._runner.run(
            [
                "nft",
                action,
                "element",
                "bridge",
                NFT_CLIENT_TABLE,
                "blocked_macs",
                "{",
                mac,
                "}",
            ]
        )
        if result.returncode != 0:
            if not blocked and _is_missing_nft_element(result):
                return DeviceCommandResult(applied=True, changed=False)
            return DeviceCommandResult(
                applied=False,
                error=(result.stderr or result.stdout or f"nft {action} element failed").strip(),
            )
        return DeviceCommandResult(applied=True, changed=True)

    def _ensure_client_block_table(self) -> DeviceCommandResult:
        existing = self._runner.run(["nft", "list", "table", "bridge", NFT_CLIENT_TABLE])
        if existing.returncode == 0:
            return DeviceCommandResult(applied=True, changed=False)
        loaded = self._runner.run(
            ["nft", "-f", "-"],
            input_text=build_client_block_nftables_rules(self._block_interface),
        )
        if loaded.returncode != 0:
            return DeviceCommandResult(
                applied=False,
                error=(loaded.stderr or loaded.stdout or "nft client table load failed").strip(),
            )
        return DeviceCommandResult(applied=True, changed=True)


def build_client_block_nftables_rules(interface: str) -> str:
    if not _valid_interface(interface):
        raise ValueError(f"invalid client block interface: {interface!r}")
    return "\n".join(
        (
            f"table bridge {NFT_CLIENT_TABLE} {{",
            "  set blocked_macs {",
            "    type ether_addr",
            "  }",
            "  chain forward {",
            "    type filter hook forward priority -300; policy accept;",
            f"    iifname \"{interface}\" ether saddr @blocked_macs drop",
            "  }",
            "}",
        )
    ) + "\n"


def build_client_rate_limit_nftables_rules(
    interface: str,
    rate_config: ClientRateConfig,
) -> str:
    if not _valid_interface(interface):
        raise ValueError(f"invalid client rate-limit interface: {interface!r}")
    lines = [
        f"table bridge {NFT_CLIENT_RATE_TABLE} {{",
        "  chain forward {",
        "    type filter hook forward priority -299; policy accept;",
    ]
    for limit in rate_config.limits:
        mac = MacAddress(limit.mac).value
        if limit.up and limit.up > 0:
            lines.append(
                f"    iifname \"{interface}\" ether saddr {mac} "
                f"limit rate over {_kbps_to_bytes_per_second(limit.up)} bytes/second drop"
            )
        if limit.down and limit.down > 0:
            lines.append(
                f"    oifname \"{interface}\" ether daddr {mac} "
                f"limit rate over {_kbps_to_bytes_per_second(limit.down)} bytes/second drop"
            )
    lines.extend(("  }", "}"))
    return "\n".join(lines) + "\n"


def _kbps_to_bytes_per_second(kbps: int) -> int:
    return max(1, int(kbps) * 1000 // 8)


def _is_missing_nft_element(result: object) -> bool:
    text = " ".join(
        str(value).lower()
        for value in (getattr(result, "stderr", ""), getattr(result, "stdout", ""))
    )
    return "no such file" in text or "does not exist" in text or "not found" in text


def _valid_interface(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_.:-]{1,32}", value))


def _valid_object_suffix(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", value))
