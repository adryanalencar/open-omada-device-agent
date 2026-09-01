"""Normalized TR-069 parameter tree for GenieACS device documents."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any

from ....shared.domain import MacAddress


class GenieAcsParameterError(ValueError):
    """A GenieACS parameter could not be normalized or coerced safely."""


@dataclass(frozen=True)
class GenieAcsParameter:
    path: str
    value: Any = None
    value_type: str | None = None
    writable: bool | None = None
    timestamp: datetime | None = None
    present: bool = True

    @classmethod
    def missing(cls, path: str) -> "GenieAcsParameter":
        return cls(path=path, present=False)

    def as_string(self, default: str | None = None) -> str | None:
        if not self.present or self.value is None:
            return default
        if isinstance(self.value, str):
            return self.value
        if isinstance(self.value, bool):
            return "true" if self.value else "false"
        return str(self.value)

    def as_bool(self, default: bool | None = None) -> bool | None:
        if not self.present or self.value is None:
            return default
        if isinstance(self.value, bool):
            return self.value
        if isinstance(self.value, int) and not isinstance(self.value, bool):
            if self.value in {0, 1}:
                return bool(self.value)
            raise GenieAcsParameterError(f"{self.path} is not a boolean value")
        if isinstance(self.value, str):
            normalized = self.value.strip().lower()
            if normalized in {"1", "true", "yes", "on", "enabled"}:
                return True
            if normalized in {"0", "false", "no", "off", "disabled"}:
                return False
        raise GenieAcsParameterError(f"{self.path} is not a boolean value")

    def as_int(self, default: int | None = None) -> int | None:
        if not self.present or self.value is None:
            return default
        if isinstance(self.value, bool):
            raise GenieAcsParameterError(f"{self.path} is not an integer value")
        try:
            return int(str(self.value), 0)
        except (TypeError, ValueError) as exc:
            raise GenieAcsParameterError(f"{self.path} is not an integer value") from exc

    def as_uint(self, default: int | None = None) -> int | None:
        value = self.as_int(default)
        if value is None:
            return None
        if value < 0:
            raise GenieAcsParameterError(f"{self.path} is not an unsigned integer value")
        return value

    def as_datetime(self, default: datetime | None = None) -> datetime | None:
        if not self.present or self.value is None:
            return default
        if isinstance(self.value, datetime):
            return _aware_utc(self.value)
        if isinstance(self.value, str):
            return _parse_datetime(self.value) or default
        raise GenieAcsParameterError(f"{self.path} is not a date/time value")

    def as_mac(self, default: str | None = None) -> str | None:
        if not self.present or self.value in (None, ""):
            return default
        try:
            return MacAddress(str(self.value)).value
        except ValueError as exc:
            raise GenieAcsParameterError(f"{self.path} is not a MAC address") from exc

    def is_stale(
        self,
        *,
        max_age_seconds: int,
        now: datetime | None = None,
    ) -> bool:
        if self.timestamp is None:
            return True
        reference = _aware_utc(now or datetime.now(timezone.utc))
        age_seconds = (reference - self.timestamp).total_seconds()
        return age_seconds > max_age_seconds


@dataclass(frozen=True)
class ParameterWrite:
    path: str
    value: Any
    value_type: str

    @classmethod
    def infer(cls, path: str, value: Any) -> "ParameterWrite":
        return cls(path=path, value=value, value_type=_infer_xsd_type(value))

    def __post_init__(self) -> None:
        _validate_parameter_path(self.path)
        if not self.value_type:
            raise GenieAcsParameterError("parameter write requires an xsd type")

    def as_task_entry(self) -> list[Any]:
        return [self.path, self.value, self.value_type]


@dataclass(frozen=True)
class ParameterTree:
    parameters: Mapping[str, GenieAcsParameter]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "parameters",
            MappingProxyType(dict(sorted(self.parameters.items()))),
        )
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    @classmethod
    def from_genieacs_device(cls, device: Mapping[str, Any]) -> "ParameterTree":
        parameters: dict[str, GenieAcsParameter] = {}
        metadata = _metadata(device)
        _collect_parameters(parameters, "", device)
        return cls(parameters=parameters, metadata=metadata)

    def get(self, path: str) -> GenieAcsParameter | None:
        return self.parameters.get(path)

    def get_or_missing(self, path: str) -> GenieAcsParameter:
        return self.parameters.get(path) or GenieAcsParameter.missing(path)

    def has(self, path: str) -> bool:
        return path in self.parameters

    def has_prefix(self, prefix: str) -> bool:
        normalized = prefix if prefix.endswith(".") else f"{prefix}."
        return any(path == prefix or path.startswith(normalized) for path in self.parameters)

    def with_prefix(self, prefix: str) -> tuple[GenieAcsParameter, ...]:
        normalized = prefix if prefix.endswith(".") else f"{prefix}."
        return tuple(
            parameter
            for path, parameter in self.parameters.items()
            if path == prefix or path.startswith(normalized)
        )

    def root_exists(self, root: str) -> bool:
        return self.has_prefix(root)

    @property
    def device_id(self) -> str | None:
        value = self.metadata.get("_id")
        return str(value) if value not in (None, "") else None

    @property
    def last_inform(self) -> datetime | None:
        value = self.metadata.get("_lastInform")
        if isinstance(value, datetime):
            return _aware_utc(value)
        if isinstance(value, str):
            return _parse_datetime(value)
        return None


def normalize_parameters(device: Mapping[str, Any]) -> ParameterTree:
    return ParameterTree.from_genieacs_device(device)


def task_entries(writes: Iterable[ParameterWrite]) -> list[list[Any]]:
    return [write.as_task_entry() for write in writes]


def _collect_parameters(
    target: dict[str, GenieAcsParameter],
    prefix: str,
    value: Any,
) -> None:
    if not isinstance(value, Mapping):
        return
    if _is_parameter_node(value):
        if not prefix:
            raise GenieAcsParameterError("GenieACS parameter node is missing a path")
        target[prefix] = _parameter_from_node(prefix, value)
        return
    for key, child in value.items():
        if prefix == "" and str(key).startswith("_"):
            continue
        child_path = str(key) if not prefix else f"{prefix}.{key}"
        _collect_parameters(target, child_path, child)


def _parameter_from_node(path: str, node: Mapping[str, Any]) -> GenieAcsParameter:
    return GenieAcsParameter(
        path=path,
        value=node.get("_value"),
        value_type=_optional_string(node.get("_type")),
        writable=_optional_bool(node.get("_writable")),
        timestamp=_parse_datetime(node.get("_timestamp")),
        present=True,
    )


def _metadata(device: Mapping[str, Any]) -> dict[str, Any]:
    return {
        str(key): value
        for key, value in device.items()
        if str(key).startswith("_") and not _is_parameter_node(value)
    }


def _is_parameter_node(value: Any) -> bool:
    return isinstance(value, Mapping) and any(
        key in value for key in ("_value", "_type", "_writable", "_timestamp")
    )


def _optional_string(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _optional_bool(value: Any) -> bool | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        if value in {0, 1}:
            return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on", "writable"}:
            return True
        if normalized in {"0", "false", "no", "off", "readonly", "read-only"}:
            return False
    raise GenieAcsParameterError(f"invalid GenieACS writable flag: {value!r}")


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return _aware_utc(value)
    if not isinstance(value, str):
        raise GenieAcsParameterError(f"invalid GenieACS timestamp: {value!r}")
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        return _aware_utc(datetime.fromisoformat(raw))
    except ValueError as exc:
        raise GenieAcsParameterError(f"invalid GenieACS timestamp: {value!r}") from exc


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _infer_xsd_type(value: Any) -> str:
    if isinstance(value, bool):
        return "xsd:boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "xsd:int" if value < 0 else "xsd:unsignedInt"
    return "xsd:string"


def _validate_parameter_path(path: str) -> None:
    if not path or any(ord(char) < 32 for char in path):
        raise GenieAcsParameterError("invalid TR-069 parameter path")
    if " " in path or ".." in path or path.startswith(".") or path.endswith("."):
        raise GenieAcsParameterError("invalid TR-069 parameter path")
