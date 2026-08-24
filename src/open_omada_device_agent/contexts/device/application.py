"""Use cases and outbound ports for applying controller configuration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ...domain import AccessPointConfigUpdate


class ReconciliationResult(Protocol):
    applied: bool
    changed: bool
    error: str


class ConfigurationPort(Protocol):
    def reconcile(
        self, update: AccessPointConfigUpdate, capabilities: object
    ) -> ReconciliationResult: ...


class CapabilityDetector(Protocol):
    def __call__(self) -> object: ...


@dataclass(frozen=True)
class ApplyConfigurationResult:
    applied: bool
    changed: bool = False
    error: str = ""


class ApplyDeviceConfiguration:
    """Coordinate independent platform adapters without knowing OpenWrt."""

    def __init__(
        self,
        *,
        capability_detector: CapabilityDetector,
        platform_ports: tuple[ConfigurationPort, ...],
        command_ports: tuple[ConfigurationPort, ...],
    ) -> None:
        self._detect = capability_detector
        self._platform_ports = platform_ports
        self._command_ports = command_ports

    def execute(self, update: AccessPointConfigUpdate) -> ApplyConfigurationResult:
        if update.unhandled_keys:
            return ApplyConfigurationResult(
                applied=False,
                error=f"unsupported keys: {','.join(update.unhandled_keys)}",
            )
        has_platform = bool(
            update.radios
            or update.wlans
            or update.management_vlan is not None
            or update.portal_free_policy is not None
        )
        has_commands = bool(
            update.led is not None
            or update.wifi_control_led is not None
            or update.client_configs
            or update.client_operations
            or update.client_rate_config is not None
        )
        if not has_platform and not has_commands:
            return ApplyConfigurationResult(applied=True)

        capabilities = self._detect()
        changed = False
        ports = (
            (self._platform_ports if has_platform else ())
            + (self._command_ports if has_commands else ())
        )
        for port in ports:
            result = port.reconcile(update, capabilities)
            if not result.applied:
                return ApplyConfigurationResult(False, changed, result.error)
            changed = changed or result.changed
        return ApplyConfigurationResult(True, changed)
