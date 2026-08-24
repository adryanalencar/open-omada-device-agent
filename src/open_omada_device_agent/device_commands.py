"""Local device command adapters for AP SET_REQUEST command-like keys."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import config
from .domain import AccessPointConfigUpdate
from .platform_capabilities import PlatformCapabilities


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
