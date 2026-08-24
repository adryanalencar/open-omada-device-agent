"""VLAN and DHCP intent, independent of UCI or a particular platform."""
from dataclasses import dataclass, field
from typing import Any, Mapping
from ...shared.domain import DomainError

class InvalidVlanId(DomainError):
    pass

@dataclass(frozen=True, order=True)
class VlanId:
    value: int
    def __post_init__(self) -> None:
        if not 1 <= int(self.value) <= 4094:
            raise InvalidVlanId(f"VLAN ID must be between 1 and 4094: {self.value}")

@dataclass(frozen=True)
class DhcpOption82:
    enabled: bool = False
    format: int | None = None
    delimiter: str | None = None
    circuit_id: tuple[int, ...] = ()
    remote_id: tuple[int, ...] = ()
    site_name: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class VlanAssignment:
    vlan_id: int | None = None
    vlan_pool_ids: tuple[str, ...] = ()
    dynamic_vlan_mode: int | None = None
    dhcp_option82: DhcpOption82 | None = None

@dataclass(frozen=True)
class ManagementVlan:
    enabled: bool
    vlan_id: int | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

def validate_vlan_id(vlan_id: int) -> int:
    return VlanId(int(vlan_id)).value
