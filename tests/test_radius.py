import hashlib
import struct

import pytest

from open_omada_device_agent.domain import PortalClientState, SecretValue
from open_omada_device_agent.portal import PortalSessionManager
from open_omada_device_agent.radius import (
    ACCESS_ACCEPT,
    ACCESS_REJECT,
    ACCESS_REQUEST,
    ATTR_CALLING_STATION_ID,
    ATTR_NAS_IDENTIFIER,
    ATTR_NAS_IP_ADDRESS,
    ATTR_SESSION_TIMEOUT,
    ATTR_USER_NAME,
    ATTR_USER_PASSWORD,
    RADIUS_HEADER,
    RadiusAttribute,
    RadiusClient,
    RadiusError,
    RadiusRequest,
    RadiusResponse,
    RadiusServer,
    authenticate_portal_client,
)


class FakeRadiusSocket:
    def __init__(
        self,
        *,
        secret: str,
        response_code: int = ACCESS_ACCEPT,
        response_attrs: tuple[bytes, ...] = (),
        corrupt_authenticator: bool = False,
    ) -> None:
        self.secret = secret
        self.response_code = response_code
        self.response_attrs = response_attrs
        self.corrupt_authenticator = corrupt_authenticator
        self.sent: list[tuple[bytes, tuple[str, int]]] = []
        self.timeout: float | None = None
        self.closed = False
        self._response = b""

    def __call__(self, _family, _sock_type):
        return self

    def settimeout(self, timeout):
        self.timeout = timeout

    def sendto(self, data, addr):
        self.sent.append((data, addr))
        _code, identifier, _length, request_auth = RADIUS_HEADER.unpack_from(data)
        self._response = _radius_response(
            self.response_code,
            identifier,
            request_auth,
            b"".join(self.response_attrs),
            self.secret,
            corrupt_authenticator=self.corrupt_authenticator,
        )

    def recvfrom(self, _size):
        return self._response, ("127.0.0.1", 1812)

    def close(self):
        self.closed = True


class StaticRadiusClient:
    def __init__(self, response: RadiusResponse | None = None, error: RadiusError | None = None):
        self.response = response
        self.error = error

    def authenticate(self, _server, _request):
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


def test_radius_client_sends_access_request_and_accepts_session_timeout():
    secret = "shared-secret"
    fake_socket = FakeRadiusSocket(
        secret=secret,
        response_attrs=(_attr(ATTR_SESSION_TIMEOUT, struct.pack("!I", 600)),),
    )
    client = RadiusClient(
        socket_factory=fake_socket,
        random_bytes=lambda size: b"\x01" * size,
    )

    response = client.authenticate(
        RadiusServer(host="radius.example.test", secret=SecretValue(secret)),
        RadiusRequest(
            username="alice",
            password=SecretValue("client-password"),
            client_mac="aa:bb:cc:dd:ee:ff",
            nas_identifier="openomada-ap",
            nas_ip_address="192.0.2.2",
        ),
    )

    assert response.accepted is True
    assert response.session_timeout == 600
    assert fake_socket.sent[0][1] == ("radius.example.test", 1812)
    assert fake_socket.closed is True

    sent_packet = fake_socket.sent[0][0]
    code, _identifier, _length, request_auth = RADIUS_HEADER.unpack_from(sent_packet)
    attrs = _parse_attrs(sent_packet[RADIUS_HEADER.size:])

    assert code == ACCESS_REQUEST
    assert request_auth == b"\x01" * 16
    assert attrs[ATTR_USER_NAME] == [b"alice"]
    assert attrs[ATTR_CALLING_STATION_ID] == [b"AA-BB-CC-DD-EE-FF"]
    assert attrs[ATTR_NAS_IDENTIFIER] == [b"openomada-ap"]
    assert attrs[ATTR_NAS_IP_ADDRESS] == [b"\xc0\x00\x02\x02"]
    assert b"client-password" not in sent_packet
    assert len(attrs[ATTR_USER_PASSWORD][0]) % 16 == 0


def test_radius_client_rejects_invalid_response_authenticator():
    fake_socket = FakeRadiusSocket(secret="shared-secret", corrupt_authenticator=True)
    client = RadiusClient(
        socket_factory=fake_socket,
        random_bytes=lambda size: b"\x02" * size,
    )

    with pytest.raises(RadiusError, match="authenticator"):
        client.authenticate(
            RadiusServer(host="127.0.0.1", secret=SecretValue("shared-secret")),
            RadiusRequest(
                username="alice",
                password=SecretValue("client-password"),
                client_mac="aa:bb:cc:dd:ee:ff",
                nas_identifier="openomada-ap",
            ),
        )


def test_portal_radius_accept_updates_session_manager():
    manager = PortalSessionManager(now=lambda: 1000)
    response = RadiusResponse(
        code=ACCESS_ACCEPT,
        identifier=1,
        attributes=(RadiusAttribute(ATTR_SESSION_TIMEOUT, struct.pack("!I", 60)),),
    )

    result = authenticate_portal_client(
        manager,
        StaticRadiusClient(response=response),
        RadiusServer(host="127.0.0.1", secret=SecretValue("shared-secret")),
        RadiusRequest(
            username="alice",
            password=SecretValue("client-password"),
            client_mac="aa:bb:cc:dd:ee:ff",
            nas_identifier="openomada-ap",
        ),
        ssid="guest",
        ipv4="192.0.2.20",
    )

    assert result.accepted is True
    assert result.session.state is PortalClientState.AUTHENTICATED
    assert result.session.username == "alice"
    assert result.session.ssid == "guest"
    assert result.session.ipv4 == "192.0.2.20"
    assert result.session.expires_at == 1060


def test_portal_radius_reject_logs_out_client():
    manager = PortalSessionManager(now=lambda: 1000)

    result = authenticate_portal_client(
        manager,
        StaticRadiusClient(response=RadiusResponse(code=ACCESS_REJECT, identifier=1)),
        RadiusServer(host="127.0.0.1", secret=SecretValue("shared-secret")),
        RadiusRequest(
            username="alice",
            password=SecretValue("client-password"),
            client_mac="aa:bb:cc:dd:ee:ff",
            nas_identifier="openomada-ap",
        ),
    )

    assert result.accepted is False
    assert result.session.state is PortalClientState.UNAUTHENTICATED


def _radius_response(
    code: int,
    identifier: int,
    request_authenticator: bytes,
    attrs: bytes,
    secret: str,
    *,
    corrupt_authenticator: bool = False,
) -> bytes:
    length = RADIUS_HEADER.size + len(attrs)
    prefix = struct.pack("!BBH", code, identifier, length)
    authenticator = hashlib.md5(prefix + request_authenticator + attrs + secret.encode()).digest()
    if corrupt_authenticator:
        authenticator = b"\x00" * 16
    return prefix + authenticator + attrs


def _attr(attr_type: int, value: bytes) -> bytes:
    return bytes((attr_type, len(value) + 2)) + value


def _parse_attrs(data: bytes) -> dict[int, list[bytes]]:
    parsed: dict[int, list[bytes]] = {}
    offset = 0
    while offset < len(data):
        attr_type = data[offset]
        attr_len = data[offset + 1]
        parsed.setdefault(attr_type, []).append(data[offset + 2 : offset + attr_len])
        offset += attr_len
    return parsed
