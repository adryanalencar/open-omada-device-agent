"""TP-Link Omada ECSP length-prefixed JSON codec (6.2.14.11 family)."""
from __future__ import annotations

import json
import socket
import struct
from enum import IntEnum
from typing import Any, Mapping

LENGTH_SIZE = 4
MAX_DISCOVERY_PAYLOAD = 2000
MAX_TCP_PAYLOAD = 8 * 1024 * 1024


class MessageType(IntEnum):
    DISCOVERY = 1
    PRE_ADOPT_REQUEST = 2
    PRE_CONNECT_INFO = 3
    ADOPT_REQUEST = 16
    ADOPT_RESPONSE = 32
    INFORM_REQUEST = 256
    INFORM_RESPONSE = 512
    EVENT_PORTAL_QUERY = 64
    EVENT_PORTAL_AUTH = 128
    EVENT_PORTAL_AUTH_RESPONSE = 352
    NOTIFY_REQUEST = 80
    NOTIFY_REPLY = 144
    SET_REQUEST = 4096
    SET_RESPONSE = 8192
    FORGET_REQUEST = 16384
    FORGET_RESPONSE = 20480
    INIT_SYNC = 4352
    GET_REQUEST = 24576
    GET_RESPONSE = 28672
    FORGET_REQUEST_NO_RESET = 131072
    FORGET_RESPONSE_NO_RESET = 196608
    PRE_CONNECT_INFO_RESPONSE = 0x100000
    DEVICE_VERIFY_INFO = 0x100001
    DEVICE_VERIFY_RESPONSE = 0x100002
    SYSTEM_VERIFY_RESULT = 0x100003
    DEVICE_NEGOTIATION = 0x100004
    SYSTEM_NEGOTIATION = 0x100005
    INIT_SYNC_RESULT = 0x100006
    NOTIFY_REQUEST_V2 = 0x100007
    NOTIFY_REPLY_V2 = 0x100008
    VERIFY_RESULT_ACK = 0x100009
    INIT_SYNC_RESULT_ACK = 0x10000A
    REPORT = 0x150000


class CipherType(IntEnum):
    SHA256 = 4
    MD5 = 5


def normalize_mac(mac: str) -> str:
    raw = mac.replace("-", "").replace(":", "").lower()
    if len(raw) != 12 or any(c not in "0123456789abcdef" for c in raw):
        raise ValueError(f"invalid MAC address: {mac!r}")
    return ":".join(raw[i : i + 2] for i in range(0, 12, 2))


def build_message(
    *,
    mac: str,
    msg_type: int | MessageType,
    body: Mapping[str, Any] | None = None,
    version: str = "2.3.0",
    ver_cap: int = 2,
    seq: int | None = 1,
    device: str = "ap",
    dest: str | None = None,
    timestamp: int | None = None,
    error: int = 0,
    include_body: bool = True,
) -> dict[str, Any]:
    header: dict[str, Any] = {}
    if seq is not None:
        header["seq"] = int(seq)
    header.update(
        {
            "version": str(version),
            "verCap": int(ver_cap),
            "device": device,
            "mac": normalize_mac(mac),
            "type": int(msg_type),
            "error": int(error),
        }
    )
    if dest:
        header["dest"] = dest
    if timestamp is not None:
        header["timestamp"] = int(timestamp)

    message: dict[str, Any] = {"header": header}
    if include_body:
        message["body"] = dict(body or {})
    return message


def encode_payload(message: Mapping[str, Any]) -> bytes:
    return json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def encode_frame(message: Mapping[str, Any]) -> bytes:
    payload = encode_payload(message)
    return struct.pack("!I", len(payload)) + payload


def decode_frame(frame: bytes) -> dict[str, Any]:
    if len(frame) < LENGTH_SIZE:
        raise ValueError("ECSP frame is shorter than its 4-byte length field")
    (declared_len,) = struct.unpack("!I", frame[:4])
    payload = frame[4:]
    if declared_len != len(payload):
        raise ValueError(
            f"ECSP payload length mismatch: declared={declared_len}, actual={len(payload)}"
        )
    obj = json.loads(payload.decode("utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("ECSP JSON root is not an object")
    return obj


def recv_exact(sock: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            raise EOFError("ECSP TCP peer closed the connection")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def recv_tcp_message(sock: socket.socket) -> tuple[dict[str, Any], bytes]:
    prefix = recv_exact(sock, 4)
    (length,) = struct.unpack("!I", prefix)
    if length <= 0 or length > MAX_TCP_PAYLOAD:
        raise ValueError(f"invalid ECSP TCP payload length: {length}")
    payload = recv_exact(sock, length)
    frame = prefix + payload
    return decode_frame(frame), frame


def send_tcp_message(sock: socket.socket, message: Mapping[str, Any]) -> bytes:
    frame = encode_frame(message)
    sock.sendall(frame)
    return frame


def message_type_name(value: int) -> str:
    try:
        return MessageType(value).name
    except ValueError:
        return f"UNKNOWN({value})"
