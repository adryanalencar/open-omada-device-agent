"""Cross-context configuration orchestration and outbound ports."""
import logging
from dataclasses import dataclass
from typing import Protocol

from .commands import ApplyDeviceConfigurationCommand
from .contracts import PlatformCapabilities

log = logging.getLogger("open_omada.config")

class ReconciliationResult(Protocol):
    applied: bool
    changed: bool
    error: str

class ConfigurationPort(Protocol):
    def reconcile(self, update: ApplyDeviceConfigurationCommand, capabilities: PlatformCapabilities) -> ReconciliationResult: ...

class CapabilityDetector(Protocol):
    def __call__(self) -> PlatformCapabilities: ...

@dataclass(frozen=True)
class ApplyConfigurationResult:
    applied: bool
    changed: bool = False
    error: str = ""

class ApplyDeviceConfiguration:
    def __init__(self, *, capability_detector: CapabilityDetector, platform_ports: tuple[ConfigurationPort, ...], command_ports: tuple[ConfigurationPort, ...], allow_ack_only_config: bool = False) -> None:
        self._detect = capability_detector
        self._platform_ports = platform_ports
        self._command_ports = command_ports
        self._allow_ack_only_config = allow_ack_only_config

    def execute(self, update: ApplyDeviceConfigurationCommand) -> ApplyConfigurationResult:
        if update.unhandled_keys:
            return ApplyConfigurationResult(False, error=f"unsupported keys: {','.join(update.unhandled_keys)}")
        if update.ack_only_keys:
            keys = ",".join(update.ack_only_keys)
            if not self._allow_ack_only_config:
                return ApplyConfigurationResult(False, error=f"ack-only control-plane keys require OMADA_LAB_ACK_CONTROL_PLANE_CONFIG=true: {keys}")
            log.warning("Acknowledging controller-side AP config without local OpenWrt changes: %s", keys)
        has_platform = bool(update.radios or update.wlans or update.management_vlan is not None or update.portal_free_policy is not None)
        has_commands = bool(update.led is not None or update.wifi_control_led is not None or update.client_configs or update.client_operations or update.client_rate_config is not None)
        if not has_platform and not has_commands:
            return ApplyConfigurationResult(True)
        capabilities = self._detect()
        changed = False
        ports = (self._platform_ports if has_platform else ()) + (self._command_ports if has_commands else ())
        for port in ports:
            result = port.reconcile(update, capabilities)
            if not result.applied:
                return ApplyConfigurationResult(False, changed, result.error)
            changed = changed or result.changed
        return ApplyConfigurationResult(True, changed)
