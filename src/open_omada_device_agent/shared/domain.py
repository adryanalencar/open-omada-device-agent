"""Value objects whose semantics are shared by multiple contexts."""
from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import re


class DomainError(ValueError):
    """Base error for a violated domain invariant."""


class InvalidMacAddress(DomainError):
    """A MAC address could not be normalized."""


@dataclass(frozen=True, order=True)
class MacAddress:
    value: str

    def __post_init__(self) -> None:
        compact = re.sub(r"[^0-9A-Fa-f]", "", self.value)
        if len(compact) != 12 or not all(char in "0123456789abcdefABCDEF" for char in compact):
            raise InvalidMacAddress(f"invalid MAC address: {self.value!r}")
        normalized = ":".join(compact[index : index + 2] for index in range(0, 12, 2)).lower()
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class IpAddress:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", str(ipaddress.ip_address(self.value)))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, repr=False)
class SecretValue:
    value: str

    def reveal(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return "SecretValue(***)"

    __str__ = __repr__
