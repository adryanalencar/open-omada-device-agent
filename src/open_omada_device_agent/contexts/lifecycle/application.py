"""Ports consumed by the managed controller lifecycle."""
from typing import Any, Protocol

from ...application.commands import ApplyDeviceConfigurationCommand
from ...application.configuration import ApplyConfigurationResult
from ...application.settings import AgentSettings
from ..device.domain import DeviceProfile
from .domain import ManagedState

class ConfigurationApplier(Protocol):
    def execute(self, update: ApplyDeviceConfigurationCommand) -> ApplyConfigurationResult: ...

class InformProvider(Protocol):
    def build(self, *, need_reply: bool, uptime: int) -> dict[str, Any]: ...

class SessionStateRepository(Protocol):
    def load(self) -> ManagedState | None: ...
    def save(self, state: ManagedState) -> ManagedState: ...
    def clear(self) -> bool: ...

class ManagedSessionServices(Protocol):
    configuration: ConfigurationApplier
    inform: InformProvider
    state_repository: SessionStateRepository
    settings: AgentSettings
    device_profile: DeviceProfile
