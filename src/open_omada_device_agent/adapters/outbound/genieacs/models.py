"""Typed GenieACS NBI results shared by adapter modules."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


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
