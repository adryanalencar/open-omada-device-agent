"""Typed GenieACS NBI results shared by adapter modules."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class Tr069DataModel(str, Enum):
    TR181 = "tr181"
    TR098 = "tr098"
    DUAL = "dual"
    UNKNOWN = "unknown"


class GenieAcsTaskState(str, Enum):
    EXECUTED = "executed"
    QUEUED = "queued"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class GenieAcsTaskResult:
    state: GenieAcsTaskState
    status_code: int
    payload: Any = None
    task_id: str | None = None
    faults: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)

    @property
    def executed(self) -> bool:
        return self.state is GenieAcsTaskState.EXECUTED

    @property
    def queued(self) -> bool:
        return self.state is GenieAcsTaskState.QUEUED

    @property
    def failed(self) -> bool:
        return self.state is GenieAcsTaskState.FAILED


@dataclass(frozen=True)
class GenieAcsDeviceIdentity:
    genieacs_id: str
    manufacturer: str | None = None
    oui: str | None = None
    product_class: str | None = None
    serial_number: str | None = None
    software_version: str | None = None
    hardware_version: str | None = None
    mac: str | None = None
    mac_source: str | None = None


@dataclass(frozen=True)
class MacCandidate:
    path: str
    role: str
    priority: int


@dataclass(frozen=True)
class MacSelection:
    mac: str
    path: str
    role: str
