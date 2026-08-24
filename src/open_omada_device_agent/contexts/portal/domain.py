"""Captive portal policy and state; enforcement belongs to infrastructure."""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

class PortalClientState(str, Enum):
    UNKNOWN = "unknown"
    UNAUTHENTICATED = "unauthenticated"
    AUTHENTICATING = "authenticating"
    AUTHENTICATED = "authenticated"
    EXPIRED = "expired"
    BLOCKED = "blocked"

@dataclass(frozen=True)
class CaptivePortalBinding:
    enabled: bool = False
    https_redirect: bool | None = None
    hotspot_v2: Mapping[str, Any] | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class PortalFreePolicy:
    layer2_rules: tuple[Mapping[str, Any], ...] = ()
    url_rules: tuple[Mapping[str, Any], ...] = ()
    raw: Mapping[str, Any] = field(default_factory=dict)
