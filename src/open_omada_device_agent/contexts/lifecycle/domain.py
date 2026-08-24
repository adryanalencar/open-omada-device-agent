"""Explicit, platform-independent controller session lifecycle."""
from dataclasses import dataclass, replace
from enum import Enum

class LifecycleState(str, Enum):
    DISCOVERING = "discovering"
    ADOPTING = "adopting"
    VERIFYING = "verifying"
    NEGOTIATING = "negotiating"
    MANAGED = "managed"
    REBUILDING = "rebuilding"
    DISCONNECTED = "disconnected"

_ALLOWED = {
    LifecycleState.DISCONNECTED: {LifecycleState.DISCOVERING, LifecycleState.REBUILDING},
    LifecycleState.DISCOVERING: {LifecycleState.ADOPTING, LifecycleState.DISCONNECTED},
    LifecycleState.ADOPTING: {LifecycleState.VERIFYING, LifecycleState.DISCONNECTED},
    LifecycleState.VERIFYING: {LifecycleState.NEGOTIATING, LifecycleState.DISCONNECTED},
    LifecycleState.NEGOTIATING: {LifecycleState.MANAGED, LifecycleState.DISCONNECTED},
    LifecycleState.MANAGED: {LifecycleState.REBUILDING, LifecycleState.DISCONNECTED},
    LifecycleState.REBUILDING: {LifecycleState.VERIFYING, LifecycleState.DISCOVERING, LifecycleState.DISCONNECTED},
}

@dataclass(frozen=True)
class ControllerSession:
    state: LifecycleState = LifecycleState.DISCONNECTED
    config_version: int | None = None
    sequence_id: int | None = None
    def transition(self, target: LifecycleState) -> "ControllerSession":
        if target not in _ALLOWED[self.state]:
            raise ValueError(f"invalid lifecycle transition: {self.state.value} -> {target.value}")
        return replace(self, state=target)

@dataclass(frozen=True)
class ManagedState:
    version: int
    mac: str
    controller_host: str
    controller_id: str
    manage_port: int
    site_id: str = ""
    username: str = ""
    config_version: int | None = None
    sequence_id: int | None = None
    updated_at: int = 0
