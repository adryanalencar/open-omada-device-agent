"""Ports consumed by the managed controller lifecycle."""
from typing import Any, Protocol

from ...application.commands import ApplyDeviceConfigurationCommand
from ...application.configuration import ApplyConfigurationResult
from .domain import ManagedState

class ConfigurationApplier(Protocol):
    def execute(self, update: ApplyDeviceConfigurationCommand) -> ApplyConfigurationResult: ...

class InformProvider(Protocol):
    def build(self, *, need_reply: bool, uptime: int) -> dict[str, Any]: ...

class SessionStateRepository(Protocol):
    def load(self) -> ManagedState | None: ...
    def save(self, *, controller_id: str, manage_port: int, site_id: str = "", username: str = "", config_version: int | None = None, sequence_id: int | None = None) -> ManagedState: ...
    def clear(self) -> bool: ...

class ManagedSessionServices(Protocol):
    configuration: ConfigurationApplier
    inform: InformProvider
    state_repository: SessionStateRepository
