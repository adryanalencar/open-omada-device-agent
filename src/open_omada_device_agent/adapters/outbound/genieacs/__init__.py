"""GenieACS outbound adapter package."""

from .client import GenieAcsNbiClient, HttpRequest, HttpResponse, StdlibHttpTransport
from .identity import extract_identity, select_identity_mac
from .models import (
    GenieAcsDeviceIdentity,
    GenieAcsTaskResult,
    GenieAcsTaskState,
    MacCandidate,
    MacSelection,
    Tr069DataModel,
)
from .parameters import GenieAcsParameter, ParameterTree, ParameterWrite

__all__ = [
    "GenieAcsDeviceIdentity",
    "GenieAcsNbiClient",
    "GenieAcsParameter",
    "GenieAcsTaskResult",
    "GenieAcsTaskState",
    "HttpRequest",
    "HttpResponse",
    "MacCandidate",
    "MacSelection",
    "ParameterTree",
    "ParameterWrite",
    "StdlibHttpTransport",
    "Tr069DataModel",
    "extract_identity",
    "select_identity_mac",
]
