"""Persist only non-secret state needed to reconnect an adopted ECSP device."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..domain import ManagedState

from ....shared.domain import MacAddress

log = logging.getLogger("open_omada.state")
STATE_VERSION = 1


def _path(path: str | os.PathLike[str]) -> Path:
    return Path(path).expanduser()


def load_state(
    path: str | os.PathLike[str],
    *,
    expected_mac: str,
    expected_controller_host: str,
) -> ManagedState | None:
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
    expected_mac = MacAddress(expected_mac).value
    if state.mac != expected_mac:
        log.info(
            "Ignoring managed-state file %s because it belongs to MAC %s, not %s",
            state_path,
            state.mac,
            expected_mac,
        )
        return None
    if state.controller_host != expected_controller_host:
        log.info(
            "Ignoring managed-state file %s because controller host changed (%s -> %s)",
            state_path,
            state.controller_host,
            expected_controller_host,
        )
        return None
    if not state.controller_id or not (1 <= state.manage_port <= 65535):
        log.warning("Ignoring incomplete managed-state file %s", state_path)
        return None
    return state


def clear_state(path: str | os.PathLike[str]) -> bool:
    state_path = _path(path)
    try:
        state_path.unlink()
        return True
    except FileNotFoundError:
        return False


class JsonSessionStateRepository:
    """JSON-file implementation of the lifecycle persistence port."""

    def __init__(self, path: str | os.PathLike[str], *, device_mac: str, controller_host: str) -> None:
        self._path = path
        self._device_mac = MacAddress(device_mac).value
        self._controller_host = controller_host

    def load(self) -> ManagedState | None:
        state = load_state(
            self._path,
            expected_mac=self._device_mac,
            expected_controller_host=self._controller_host,
        )
        if state is None:
            return None
        if state.mac != self._device_mac or state.controller_host != self._controller_host:
            return None
        return state

    def save(self, state: ManagedState) -> ManagedState:
        if state.mac != self._device_mac or state.controller_host != self._controller_host:
            raise ValueError("managed state identity does not match repository identity")
        state_path = Path(self._path).expanduser()
        state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = state_path.with_name(state_path.name + ".tmp")
        tmp_path.write_text(
            json.dumps(asdict(state), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp_path, state_path)
        return state

    def clear(self) -> bool:
        return clear_state(self._path)
