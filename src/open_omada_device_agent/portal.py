"""Captive portal client session lifecycle."""
from __future__ import annotations

import time
from dataclasses import dataclass, replace
from typing import Callable

from .domain import PortalClientState
from .ecsp import normalize_mac


Now = Callable[[], float]


@dataclass(frozen=True)
class PortalSession:
    mac: str
    state: PortalClientState
    ssid: str | None = None
    ipv4: str | None = None
    username: str | None = None
    token: str | None = None
    created_at: int = 0
    updated_at: int = 0
    authenticated_at: int | None = None
    expires_at: int | None = None
    idle_timeout: int | None = None
    rx_bytes: int = 0
    tx_bytes: int = 0

    @property
    def authenticated(self) -> bool:
        return self.state is PortalClientState.AUTHENTICATED


class PortalSessionManager:
    def __init__(self, *, now: Now | None = None) -> None:
        self._now = now or time.time
        self._sessions: dict[str, PortalSession] = {}

    def observe_client(
        self,
        mac: str,
        *,
        ssid: str | None = None,
        ipv4: str | None = None,
    ) -> PortalSession:
        normalized = normalize_mac(mac)
        current = self._sessions.get(normalized)
        now = self._epoch()
        if current is None:
            session = PortalSession(
                mac=normalized,
                state=PortalClientState.UNAUTHENTICATED,
                ssid=ssid,
                ipv4=ipv4,
                created_at=now,
                updated_at=now,
            )
        else:
            session = replace(
                current,
                ssid=ssid or current.ssid,
                ipv4=ipv4 or current.ipv4,
                updated_at=now,
            )
        self._sessions[normalized] = session
        return session

    def start_authentication(self, mac: str) -> PortalSession:
        return self._transition(mac, PortalClientState.AUTHENTICATING)

    def authenticate(
        self,
        mac: str,
        *,
        username: str | None = None,
        token: str | None = None,
        session_timeout: int | None = None,
    ) -> PortalSession:
        normalized = normalize_mac(mac)
        current = self._sessions.get(normalized) or self.observe_client(normalized)
        now = self._epoch()
        session = replace(
            current,
            state=PortalClientState.AUTHENTICATED,
            username=username,
            token=token,
            authenticated_at=now,
            expires_at=now + int(session_timeout) if session_timeout else None,
            updated_at=now,
        )
        self._sessions[normalized] = session
        return session

    def logout(self, mac: str) -> PortalSession:
        return self._transition(mac, PortalClientState.UNAUTHENTICATED, clear_auth=True)

    def block(self, mac: str) -> PortalSession:
        return self._transition(mac, PortalClientState.BLOCKED, clear_auth=True)

    def expire_due_sessions(self) -> tuple[PortalSession, ...]:
        now = self._epoch()
        expired = []
        for session in tuple(self._sessions.values()):
            if (
                session.state is PortalClientState.AUTHENTICATED
                and session.expires_at is not None
                and session.expires_at <= now
            ):
                expired.append(self._transition(session.mac, PortalClientState.EXPIRED, clear_auth=True))
        return tuple(expired)

    def update_traffic(self, mac: str, *, rx_bytes: int = 0, tx_bytes: int = 0) -> PortalSession:
        normalized = normalize_mac(mac)
        current = self._sessions.get(normalized) or self.observe_client(normalized)
        session = replace(
            current,
            rx_bytes=max(0, int(rx_bytes)),
            tx_bytes=max(0, int(tx_bytes)),
            updated_at=self._epoch(),
        )
        self._sessions[normalized] = session
        return session

    def get(self, mac: str) -> PortalSession | None:
        return self._sessions.get(normalize_mac(mac))

    def sessions(self) -> tuple[PortalSession, ...]:
        return tuple(sorted(self._sessions.values(), key=lambda session: session.mac))

    def _transition(
        self,
        mac: str,
        state: PortalClientState,
        *,
        clear_auth: bool = False,
    ) -> PortalSession:
        normalized = normalize_mac(mac)
        current = self._sessions.get(normalized) or self.observe_client(normalized)
        session = replace(
            current,
            state=state,
            username=None if clear_auth else current.username,
            token=None if clear_auth else current.token,
            authenticated_at=None if clear_auth else current.authenticated_at,
            expires_at=None if clear_auth else current.expires_at,
            updated_at=self._epoch(),
        )
        self._sessions[normalized] = session
        return session

    def _epoch(self) -> int:
        return int(self._now())
