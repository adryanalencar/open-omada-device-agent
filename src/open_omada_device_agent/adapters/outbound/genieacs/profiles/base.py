"""Base contracts and helpers for GenieACS TR-069 profiles."""
from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from .....contexts.wireless.domain import RadioBand
from ..models import (
    GenieAcsCapabilities,
    GenieAcsDeviceIdentity,
    Tr069DataModel,
    Tr069ObjectRef,
)
from ..parameters import ParameterTree


class Tr069DeviceProfile(Protocol):
    name: str
    data_model: Tr069DataModel

    def matches(self, tree: ParameterTree) -> bool: ...
    def identity(
        self,
        tree: ParameterTree,
        *,
        preferred_mac_paths: Iterable[str] = (),
    ) -> GenieAcsDeviceIdentity: ...
    def capabilities(self, tree: ParameterTree) -> GenieAcsCapabilities: ...
    def radio_refs(self, tree: ParameterTree) -> tuple[Tr069ObjectRef, ...]: ...
    def ssid_refs(self, tree: ParameterTree) -> tuple[Tr069ObjectRef, ...]: ...
    def access_point_refs(self, tree: ParameterTree) -> tuple[Tr069ObjectRef, ...]: ...
    def client_table_refs(self, tree: ParameterTree) -> tuple[Tr069ObjectRef, ...]: ...


class UnsupportedTr069Profile:
    name = "unsupported"
    data_model = Tr069DataModel.UNKNOWN

    def matches(self, tree: ParameterTree) -> bool:
        return False

    def identity(
        self,
        tree: ParameterTree,
        *,
        preferred_mac_paths: Iterable[str] = (),
    ) -> GenieAcsDeviceIdentity:
        raise ValueError("unsupported TR-069 parameter tree")

    def capabilities(self, tree: ParameterTree) -> GenieAcsCapabilities:
        return GenieAcsCapabilities(profile=self.name, data_model=self.data_model)

    def radio_refs(self, tree: ParameterTree) -> tuple[Tr069ObjectRef, ...]:
        return ()

    def ssid_refs(self, tree: ParameterTree) -> tuple[Tr069ObjectRef, ...]:
        return ()

    def access_point_refs(self, tree: ParameterTree) -> tuple[Tr069ObjectRef, ...]:
        return ()

    def client_table_refs(self, tree: ParameterTree) -> tuple[Tr069ObjectRef, ...]:
        return ()


def select_profile(tree: ParameterTree) -> Tr069DeviceProfile:
    from .tr098 import GenericTr098Profile
    from .tr181 import GenericTr181Profile

    tr181 = GenericTr181Profile()
    tr098 = GenericTr098Profile()
    if tr181.matches(tree):
        return tr181
    if tr098.matches(tree):
        return tr098
    return UnsupportedTr069Profile()


def instance_refs(tree: ParameterTree, collection_prefix: str) -> tuple[Tr069ObjectRef, ...]:
    prefix = collection_prefix.rstrip(".")
    instances: set[str] = set()
    marker = f"{prefix}."
    for path in tree.parameters:
        if not path.startswith(marker):
            continue
        remainder = path[len(marker):]
        instance = remainder.split(".", 1)[0]
        if instance:
            instances.add(instance)
    return tuple(
        Tr069ObjectRef(path=f"{prefix}.{instance}", instance=instance)
        for instance in sorted(instances, key=_instance_sort_key)
    )


def has_any_prefix(tree: ParameterTree, prefixes: Iterable[str]) -> bool:
    return any(tree.has_prefix(prefix) for prefix in prefixes)


def any_writable(tree: ParameterTree, paths: Iterable[str]) -> bool:
    return any(tree.get_or_missing(path).writable is True for path in paths)


def path_exists(tree: ParameterTree, paths: Iterable[str]) -> bool:
    return any(tree.get(path) is not None for path in paths)


def band_from_value(value: object) -> RadioBand | None:
    if value in (None, ""):
        return None
    normalized = str(value).strip().lower().replace(" ", "")
    if normalized in {"2.4ghz", "2.4g", "2g", "2_4ghz"}:
        return RadioBand.TWO_G
    if normalized in {"5ghz", "5g"}:
        return RadioBand.FIVE_G
    if normalized in {"6ghz", "6g"}:
        return RadioBand.SIX_G
    return None


def _instance_sort_key(value: str) -> tuple[int, int | str]:
    return (0, int(value)) if value.isdigit() else (1, value)
