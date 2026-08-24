"""Local device command adapters for AP SET_REQUEST command-like keys."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from . import config
from .domain import AccessPointConfigUpdate, ClientOperationCode
from .ecsp import normalize_mac
from .openwrt import CommandRunner, SubprocessRunner
from .platform_capabilities import PlatformCapabilities

NFT_CLIENT_TABLE = "openomada_clients"


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
        on_value: str | None = None,
        off_value: str | None = None,
    ) -> None:
        self._brightness_path = brightness_path if brightness_path is not None else config.LED_BRIGHTNESS_PATH
        self._on_value = config.LED_ON_VALUE if on_value is None else on_value
        self._off_value = config.LED_OFF_VALUE if off_value is None else off_value

    def validate_update(
        self,
        update: AccessPointConfigUpdate,
        capabilities: PlatformCapabilities,
    ) -> tuple[str, ...]:
        errors = []
        if update.wifi_control_led is not None:
            errors.append("WiFi control LED reconciliation is not implemented")
        if update.led is None:
            return tuple(errors)
        if update.led.locate is not None:
            errors.append("LED locate reconciliation is not implemented")
        if update.led.enabled is not None and not capabilities.supports_led_control:
            errors.append("LED control requested but platform capability is disabled")
        if update.led.enabled is not None and not self._brightness_path:
            errors.append("LED brightness path is not configured")
        return tuple(dict.fromkeys(errors))

    def reconcile(
        self,
        update: AccessPointConfigUpdate,
        capabilities: PlatformCapabilities,
    ) -> DeviceCommandResult:
        errors = self.validate_update(update, capabilities)
        if errors:
            return DeviceCommandResult(applied=False, error="; ".join(errors))
        if update.led is None or update.led.enabled is None:
            return DeviceCommandResult(applied=True, changed=False)
        value = self._on_value if update.led.enabled else self._off_value
        try:
            Path(self._brightness_path).write_text(str(value) + "\n", encoding="ascii")
        except OSError as exc:
            return DeviceCommandResult(applied=False, error=f"LED brightness write failed: {exc}")
        return DeviceCommandResult(applied=True, changed=True)


class OpenWrtClientControlAdapter:
    def __init__(
        self,
        runner: CommandRunner | None = None,
        *,
        hostapd_iface: str | None = None,
        block_interface: str | None = None,
    ) -> None:
        self._runner = runner or SubprocessRunner()
        self._hostapd_iface = (
            config.HOSTAPD_UBUS_IFACE if hostapd_iface is None else hostapd_iface
        )
        self._block_interface = (
            config.CLIENT_BLOCK_INTERFACE if block_interface is None else block_interface
        )

    def validate_update(
        self,
        update: AccessPointConfigUpdate,
        capabilities: PlatformCapabilities,
    ) -> tuple[str, ...]:
        errors: list[str] = []
        if update.client_configs:
            errors.append("clientConfig unauth reconciliation is not implemented")
        if update.client_rate_config is not None:
            errors.append("client rate-limit reconciliation is not implemented")
        if not update.client_operations:
            return tuple(errors)
        if not capabilities.supports_client_operations:
            errors.append("client operations requested but platform capability is disabled")

        needs_hostapd = False
        needs_nft = False
        for operation in update.client_operations:
            code = operation.operation_code
            try:
                normalize_mac(operation.client_mac)
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
        update: AccessPointConfigUpdate,
        capabilities: PlatformCapabilities,
    ) -> DeviceCommandResult:
        errors = self.validate_update(update, capabilities)
        if errors:
            return DeviceCommandResult(applied=False, error="; ".join(errors))
        if not update.client_operations:
            return DeviceCommandResult(applied=True, changed=False)

        changed = False
        for operation in update.client_operations:
            code = operation.operation_code
            mac = normalize_mac(operation.client_mac)
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
