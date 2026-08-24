"""Compatibility façade for lifecycle JSON persistence."""
from __future__ import annotations

import time
from pathlib import Path

from . import config
from .contexts.lifecycle.domain import ManagedState
from .contexts.lifecycle.infrastructure.session_state import (
    JsonSessionStateRepository,
    clear_state as _clear_state,
    load_state as _load_state,
)
from .shared.domain import MacAddress


def _repository(path: str | Path | None = None) -> JsonSessionStateRepository:
    return JsonSessionStateRepository(
        path or config.STATE_FILE,
        device_mac=config.MAC,
        controller_host=config.CONTROLLER_HOST,
    )


def load_state(path: str | Path | None = None) -> ManagedState | None:
    return _load_state(
        path or config.STATE_FILE,
        expected_mac=config.MAC,
        expected_controller_host=config.CONTROLLER_HOST,
    )


def save_state(
    *,
    controller_id: str,
    manage_port: int,
    site_id: str = "",
    username: str = "",
    config_version: int | None = None,
    sequence_id: int | None = None,
    path: str | Path | None = None,
) -> ManagedState:
    state = ManagedState(
        version=1,
        mac=MacAddress(config.MAC).value,
        controller_host=config.CONTROLLER_HOST,
        controller_id=controller_id,
        manage_port=int(manage_port),
        site_id=site_id,
        username=username,
        config_version=config_version,
        sequence_id=sequence_id,
        updated_at=int(time.time()),
    )
    return _repository(path).save(state)


def clear_state(path: str | Path | None = None) -> bool:
    return _clear_state(path or config.STATE_FILE)


__all__ = ["JsonSessionStateRepository", "ManagedState", "clear_state", "load_state", "save_state"]
