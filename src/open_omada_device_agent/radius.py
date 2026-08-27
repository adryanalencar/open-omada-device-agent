"""Minimal RADIUS client for captive-portal authentication."""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import os
import socket
import struct
from collections.abc import Callable
from dataclasses import dataclass, field

from .domain import SecretValue
from .portal import PortalSession, PortalSessionManager
from .util.mac_format import to_omada

ACCESS_REQUEST = 1
ACCESS_ACCEPT = 2
ACCESS_REJECT = 3
ACCESS_CHALLENGE = 11

ATTR_USER_NAME = 1
ATTR_USER_PASSWORD = 2
ATTR_NAS_IP_ADDRESS = 4
ATTR_REPLY_MESSAGE = 18
ATTR_STATE = 24
ATTR_CLASS = 25
ATTR_SESSION_TIMEOUT = 27
ATTR_CALLED_STATION_ID = 30
ATTR_CALLING_STATION_ID = 31
ATTR_NAS_IDENTIFIER = 32

RADIUS_HEADER = struct.Struct("!BBH16s")
MAX_RADIUS_PACKET = 4096
MAX_RADIUS_PASSWORD = 128

RandomBytes = Callable[[int], bytes]
SocketFactory = Callable[[int, int], socket.socket]


class RadiusError(RuntimeError):
    """RADIUS transport or packet validation failed."""


@dataclass(frozen=True)
class RadiusServer:
    host: str
    secret: SecretValue = field(repr=False)
    port: int = 1812
    timeout: float = 3.0
    retries: int = 2


@dataclass(frozen=True)
class RadiusRequest:
    username: str
    password: SecretValue = field(repr=False)
    client_mac: str
    nas_identifier: str
    nas_ip_address: str | None = None
    ap_mac: str | None = None
    state: bytes | None = None


@dataclass(frozen=True)
class RadiusAttribute:
    type: int
    value: bytes

    def text(self) -> str:
        return self.value.decode("utf-8", errors="replace")

    def uint32(self) -> int:
        if len(self.value) != 4:
            raise RadiusError(f"RADIUS attribute {self.type} is not a uint32")
        return struct.unpack("!I", self.value)[0]


@dataclass(frozen=True)
class RadiusResponse:
    code: int
    identifier: int
    attributes: tuple[RadiusAttribute, ...] = ()

    @property
    def accepted(self) -> bool:
        return self.code == ACCESS_ACCEPT

    @property
    def rejected(self) -> bool:
        return self.code == ACCESS_REJECT

    @property
    def challenge(self) -> bool:
        return self.code == ACCESS_CHALLENGE

    @property
    def session_timeout(self) -> int | None:
        attr = self.first(ATTR_SESSION_TIMEOUT)
        return attr.uint32() if attr is not None else None

    @property
    def state(self) -> bytes | None:
        attr = self.first(ATTR_STATE)
        return attr.value if attr is not None else None

    @property
    def reply_message(self) -> str | None:
        attr = self.first(ATTR_REPLY_MESSAGE)
        return attr.text() if attr is not None else None

    def first(self, attr_type: int) -> RadiusAttribute | None:
        for attr in self.attributes:
            if attr.type == attr_type:
                return attr
        return None


@dataclass(frozen=True)
class PortalRadiusResult:
    accepted: bool
    session: PortalSession
    response: RadiusResponse | None = None
    error: str = ""


class RadiusClient:
    def __init__(
        self,
        *,
        socket_factory: SocketFactory | None = None,
        random_bytes: RandomBytes | None = None,
    ) -> None:
        self._socket_factory = socket_factory or socket.socket
        self._random_bytes = random_bytes or os.urandom
        self._identifier = 0

    def authenticate(self, server: RadiusServer, request: RadiusRequest) -> RadiusResponse:
        if not 1 <= int(server.port) <= 65535:
            raise RadiusError(f"invalid RADIUS server port: {server.port}")
        retries = max(1, int(server.retries))
        identifier = self._next_identifier()
        request_authenticator = self._random_bytes(16)
        if len(request_authenticator) != 16:
            raise RadiusError("RADIUS request authenticator must be 16 bytes")
        packet = encode_access_request(
            identifier=identifier,
            request_authenticator=request_authenticator,
            server_secret=server.secret,
            request=request,
        )

        sock = self._socket_factory(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.settimeout(float(server.timeout))
            for _attempt in range(retries):
                sock.sendto(packet, (server.host, int(server.port)))
                try:
                    data, _addr = sock.recvfrom(MAX_RADIUS_PACKET)
                except TimeoutError:
                    continue
                except socket.timeout:
                    continue
                return decode_response(
                    data,
                    server_secret=server.secret,
                    request_authenticator=request_authenticator,
                    expected_identifier=identifier,
                )
        finally:
            sock.close()
        raise RadiusError("RADIUS authentication timed out")

    def _next_identifier(self) -> int:
        self._identifier = (self._identifier + 1) & 0xFF
        return self._identifier


def authenticate_portal_client(
    manager: PortalSessionManager,
    client: RadiusClient,
    server: RadiusServer,
    request: RadiusRequest,
    *,
    ssid: str | None = None,
    ipv4: str | None = None,
) -> PortalRadiusResult:
    manager.observe_client(request.client_mac, ssid=ssid, ipv4=ipv4)
    session = manager.start_authentication(request.client_mac)
    try:
        response = client.authenticate(server, request)
    except RadiusError as exc:
        session = manager.logout(request.client_mac)
        return PortalRadiusResult(accepted=False, session=session, error=str(exc))

    if response.accepted:
        session = manager.authenticate(
            request.client_mac,
            username=request.username,
            session_timeout=response.session_timeout,
        )
        return PortalRadiusResult(accepted=True, session=session, response=response)

    if response.challenge:
        session = manager.start_authentication(request.client_mac)
        return PortalRadiusResult(
            accepted=False,
            session=session,
            response=response,
            error="RADIUS Access-Challenge is not implemented",
        )

    session = manager.logout(request.client_mac)
    return PortalRadiusResult(accepted=False, session=session, response=response)


def encode_access_request(
    *,
    identifier: int,
    request_authenticator: bytes,
    server_secret: SecretValue,
    request: RadiusRequest,
) -> bytes:
    attrs = [
        _attribute(ATTR_USER_NAME, _text(request.username)),
        _attribute(
            ATTR_USER_PASSWORD,
            _encrypt_user_password(request.password.reveal(), server_secret, request_authenticator),
        ),
        _attribute(ATTR_CALLING_STATION_ID, _text(_radius_mac(request.client_mac))),
        _attribute(ATTR_NAS_IDENTIFIER, _text(request.nas_identifier)),
    ]
    if request.ap_mac:
        attrs.append(_attribute(ATTR_CALLED_STATION_ID, _text(_radius_mac(request.ap_mac))))
    if request.nas_ip_address:
        attrs.append(
            _attribute(
                ATTR_NAS_IP_ADDRESS,
                ipaddress.ip_address(request.nas_ip_address).packed,
            )
        )
    if request.state:
        attrs.append(_attribute(ATTR_STATE, request.state))
    payload = b"".join(attrs)
    length = RADIUS_HEADER.size + len(payload)
    if length > MAX_RADIUS_PACKET:
        raise RadiusError("RADIUS Access-Request is too large")
    header = RADIUS_HEADER.pack(
        ACCESS_REQUEST,
        int(identifier) & 0xFF,
        length,
        request_authenticator,
    )
    return header + payload


def decode_response(
    packet: bytes,
    *,
    server_secret: SecretValue,
    request_authenticator: bytes,
    expected_identifier: int,
) -> RadiusResponse:
    if len(packet) < RADIUS_HEADER.size:
        raise RadiusError("RADIUS response is shorter than the header")
    code, identifier, length, response_authenticator = RADIUS_HEADER.unpack_from(packet)
    if identifier != (int(expected_identifier) & 0xFF):
        raise RadiusError("RADIUS response identifier does not match the request")
    if length < RADIUS_HEADER.size or length > len(packet):
        raise RadiusError("RADIUS response length is invalid")
    response = packet[:length]
    attributes = response[RADIUS_HEADER.size:]
    expected_authenticator = hashlib.md5(
        response[:4] + request_authenticator + attributes + server_secret.reveal().encode()
    ).digest()
    if not hmac.compare_digest(response_authenticator, expected_authenticator):
        raise RadiusError("RADIUS response authenticator is invalid")
    if code not in {ACCESS_ACCEPT, ACCESS_REJECT, ACCESS_CHALLENGE}:
        raise RadiusError(f"unsupported RADIUS response code: {code}")
    return RadiusResponse(
        code=code,
        identifier=identifier,
        attributes=_parse_attributes(attributes),
    )


def _parse_attributes(data: bytes) -> tuple[RadiusAttribute, ...]:
    attrs = []
    offset = 0
    while offset < len(data):
        if offset + 2 > len(data):
            raise RadiusError("RADIUS attribute header is truncated")
        attr_type = data[offset]
        attr_len = data[offset + 1]
        if attr_len < 2 or offset + attr_len > len(data):
            raise RadiusError("RADIUS attribute length is invalid")
        attrs.append(RadiusAttribute(attr_type, data[offset + 2 : offset + attr_len]))
        offset += attr_len
    return tuple(attrs)


def _encrypt_user_password(
    password: str,
    server_secret: SecretValue,
    request_authenticator: bytes,
) -> bytes:
    raw_password = password.encode("utf-8")
    if len(raw_password) > MAX_RADIUS_PASSWORD:
        raise RadiusError("RADIUS PAP password is longer than 128 bytes")
    padded_length = max(16, ((len(raw_password) + 15) // 16) * 16)
    padded = raw_password.ljust(padded_length, b"\x00")
    secret = server_secret.reveal().encode()
    previous = request_authenticator
    blocks = []
    for offset in range(0, len(padded), 16):
        digest = hashlib.md5(secret + previous).digest()
        block = bytes(a ^ b for a, b in zip(padded[offset : offset + 16], digest))
        blocks.append(block)
        previous = block
    return b"".join(blocks)


def _attribute(attr_type: int, value: bytes) -> bytes:
    if len(value) > 253:
        raise RadiusError(f"RADIUS attribute {attr_type} is too large")
    return bytes((int(attr_type) & 0xFF, len(value) + 2)) + value


def _text(value: str) -> bytes:
    return value.encode("utf-8")


def _radius_mac(value: str) -> str:
    return to_omada(value)
