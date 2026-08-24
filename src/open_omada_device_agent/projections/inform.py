"""Assemble domain observations into the ECSP inform read model."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from ..contexts.clients.domain import WirelessClientState

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
        info["upTime"] = str(max(0, uptime))
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
            body["clients"] = self._client_projection(clients)
        body.update(self._wireless_projection())
        return body
