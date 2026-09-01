"""GenieACS outbound adapter package."""

from .client import GenieAcsNbiClient, HttpRequest, HttpResponse, StdlibHttpTransport
from .identity import extract_identity, select_identity_mac
from .models import (
    GenieAcsCapabilities,
    GenieAcsDeviceIdentity,
    GenieAcsTaskResult,
    GenieAcsTaskState,
    MacCandidate,
    MacSelection,
    Tr069DataModel,
    Tr069ObjectRef,
)
from .parameters import GenieAcsParameter, ParameterTree, ParameterWrite
from .profiles import GenericTr098Profile, GenericTr181Profile, select_profile

__all__ = [
    "GenieAcsCapabilities",
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
    "Tr069ObjectRef",
    "GenericTr098Profile",
    "GenericTr181Profile",
    "extract_identity",
    "select_profile",
    "select_identity_mac",
]
