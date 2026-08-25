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

@dataclass(frozen=True)
class PortalConfiguration:
    auth_type: int | None = None
    auth_timeout: int | None = None
    portal_day: int | None = None
    portal_hour: int | None = None
    portal_min: int | None = None
    https_redirect_enable: bool | None = None
    redirect: bool | None = None
    redirect_url: str | None = None
    auth_server_type: int | None = None
    ext_auth_server: str | None = None
    external_portal_server: str | None = None
    portal_title: str | None = None
    portal_accept: bool | None = None
    ssid_list: tuple[str, ...] = ()
    raw: Mapping[str, Any] = field(default_factory=dict)
