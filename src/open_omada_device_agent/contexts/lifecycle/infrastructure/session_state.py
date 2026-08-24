"""Persist only non-secret state needed to reconnect an adopted ECSP device."""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..domain import ManagedState

from .... import config
from ....shared.domain import MacAddress

log = logging.getLogger("open_omada.state")
STATE_VERSION = 1


def _path(path: str | os.PathLike[str] | None = None) -> Path:
    return Path(path or config.STATE_FILE).expanduser()


def load_state(path: str | os.PathLike[str] | None = None) -> ManagedState | None:
    state_path = _path(path)
    try:
        raw: Any = json.loads(state_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError, TypeError) as exc:
        log.warning("Ignoring unreadable managed-state file %s: %s", state_path, exc)
        return None

    if not isinstance(raw, dict):
        log.warning("Ignoring invalid managed-state file %s: root is not an object", state_path)
        return None

    try:
        state = ManagedState(
            version=int(raw.get("version", 0)),
            mac=MacAddress(str(raw["mac"])).value,
            controller_host=str(raw["controller_host"]),
            controller_id=str(raw["controller_id"]),
            manage_port=int(raw["manage_port"]),
            site_id=str(raw.get("site_id") or ""),
            username=str(raw.get("username") or ""),
            config_version=(
                int(raw["config_version"])
                if raw.get("config_version") is not None
                else None
            ),
            sequence_id=(
                int(raw["sequence_id"])
                if raw.get("sequence_id") is not None
                else None
            ),
            updated_at=int(raw.get("updated_at") or 0),
        )
    except (KeyError, TypeError, ValueError) as exc:
        log.warning("Ignoring invalid managed-state file %s: %s", state_path, exc)
        return None

    if state.version != STATE_VERSION:
        log.warning(
            "Ignoring managed-state file %s with unsupported version %s",
            state_path,
            state.version,
        )
        return None
    if state.mac != MacAddress(config.MAC).value:
        log.info(
            "Ignoring managed-state file %s because it belongs to MAC %s, not %s",
            state_path,
            state.mac,
            MacAddress(config.MAC).value,
        )
        return None
    if state.controller_host != config.CONTROLLER_HOST:
        log.info(
            "Ignoring managed-state file %s because controller host changed (%s -> %s)",
            state_path,
            state.controller_host,
            config.CONTROLLER_HOST,
        )
        return None
    if not state.controller_id or not (1 <= state.manage_port <= 65535):
        log.warning("Ignoring incomplete managed-state file %s", state_path)
        return None
    return state


def save_state(
    *,
    controller_id: str,
    manage_port: int,
    site_id: str = "",
    username: str = "",
    config_version: int | None = None,
    sequence_id: int | None = None,
    path: str | os.PathLike[str] | None = None,
) -> ManagedState:
    state = ManagedState(
        version=STATE_VERSION,
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
    state_path = _path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = state_path.with_name(state_path.name + ".tmp")
    tmp_path.write_text(
        json.dumps(asdict(state), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp_path, state_path)
    return state


def clear_state(path: str | os.PathLike[str] | None = None) -> bool:
    state_path = _path(path)
    try:
        state_path.unlink()
        return True
    except FileNotFoundError:
        return False


class JsonSessionStateRepository:
    """JSON-file implementation of the lifecycle persistence port."""

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self._path = path

    def load(self) -> ManagedState | None:
        return load_state(self._path)

    def save(self, **state: Any) -> ManagedState:
        return save_state(path=self._path, **state)

    def clear(self) -> bool:
        return clear_state(self._path)
