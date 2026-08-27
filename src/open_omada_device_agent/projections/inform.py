"""Assemble domain observations into the ECSP inform read model."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from ..contexts.clients.domain import ClientPortalState, WirelessClientState

@dataclass(frozen=True)
class LanObservation:
    rate: float
    duplex: int
    port: str

class InformAssembler:
    def __init__(
        self,
        *,
        device_info: Callable[[], Mapping[str, Any]],
        lan: LanObservation,
        clients: Callable[[], tuple[WirelessClientState, ...]],
        client_projection: Callable[[tuple[WirelessClientState, ...]], list[dict[str, Any]]],
        wireless_projection: Callable[[], Mapping[str, Any]],
    ) -> None:
        self._device_info = device_info
        self._lan = lan
        self._clients = clients
        self._client_projection = client_projection
        self._wireless_projection = wireless_projection

    def build(self, *, need_reply: bool, uptime: int) -> dict[str, Any]:
        info = dict(self._device_info())
        info["isFactory"] = False
        info["upTime"] = _uptime_value(info.get("upTime"), fallback=uptime)
        body: dict[str, Any] = {
            "needReply": 1 if need_reply else 0,
            "deviceInfo": info,
            "lanInfo": {
                "rate": str(self._lan.rate),
                "duplex": self._lan.duplex,
                "port": self._lan.port,
            },
        }
        clients = self._clients()
        if clients:
            projected_clients = self._client_projection(clients)
            body["clients"] = projected_clients
            portal_clients = [
                projected
                for client, projected in zip(clients, projected_clients, strict=False)
                if client.portal_state is not ClientPortalState.UNKNOWN
            ]
            if portal_clients:
                body["portalAuthClients"] = portal_clients
        body.update(self._wireless_projection())
        return body


def _uptime_value(value: Any, *, fallback: int) -> str:
    if value not in (None, ""):
        try:
            return str(max(0, int(float(value))))
        except (TypeError, ValueError):
            return str(value)
    return str(max(0, fallback))
