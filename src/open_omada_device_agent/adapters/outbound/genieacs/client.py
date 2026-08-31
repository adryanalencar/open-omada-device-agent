"""Small GenieACS NBI HTTP client.

This module is an outbound adapter. It knows GenieACS HTTP/NBI mechanics, but
it does not know Omada ECSP message handlers or OpenWrt command syntax.
"""
from __future__ import annotations

import base64
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from pathlib import Path
import socket
import ssl
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen

from .models import GenieAcsTaskResult, GenieAcsTaskState

DEFAULT_MAX_RESPONSE_BYTES = 1024 * 1024


class GenieAcsError(RuntimeError):
    """Base error for GenieACS adapter failures."""


class GenieAcsTransportError(GenieAcsError):
    """The NBI request failed before a HTTP response was available."""


class GenieAcsTimeout(GenieAcsTransportError):
    """The NBI request exceeded its timeout."""


class GenieAcsResponseTooLarge(GenieAcsTransportError):
    """The NBI response exceeded the configured byte limit."""


class GenieAcsHttpError(GenieAcsError):
    def __init__(self, status_code: int, *, method: str, path: str, body: bytes = b"") -> None:
        self.status_code = status_code
        self.method = method
        self.path = path
        self.body_preview = _body_preview(body)
        super().__init__(
            f"GenieACS {method} {path} returned HTTP {status_code}: {self.body_preview}"
        )


class GenieAcsJsonError(GenieAcsError):
    """The NBI response was not valid JSON."""


class GenieAcsUnexpectedResponse(GenieAcsError):
    """The NBI response shape did not match the requested operation."""


@dataclass(frozen=True)
class HttpRequest:
    method: str
    url: str
    headers: Mapping[str, str]
    body: bytes | None
    timeout_seconds: float
    verify_tls: bool
    ca_bundle: Path | None
    max_response_bytes: int


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    headers: Mapping[str, str]
    body: bytes


class HttpTransport(Protocol):
    def request(self, request: HttpRequest) -> HttpResponse: ...


class StdlibHttpTransport:
    """HTTP transport implemented with the Python standard library."""

    def request(self, request: HttpRequest) -> HttpResponse:
        body = request.body
        http_request = Request(
            request.url,
            data=body,
            headers=dict(request.headers),
            method=request.method,
        )
        context = _ssl_context(request.verify_tls, request.ca_bundle)
        try:
            with urlopen(
                http_request,
                timeout=request.timeout_seconds,
                context=context,
            ) as response:
                return HttpResponse(
                    status_code=response.status,
                    headers=dict(response.headers.items()),
                    body=_read_bounded(response, request.max_response_bytes),
                )
        except HTTPError as exc:
            return HttpResponse(
                status_code=exc.code,
                headers=dict(exc.headers.items()) if exc.headers else {},
                body=_read_bounded(exc, request.max_response_bytes),
            )
        except TimeoutError as exc:
            raise GenieAcsTimeout("GenieACS request timed out") from exc
        except socket.timeout as exc:
            raise GenieAcsTimeout("GenieACS request timed out") from exc
        except URLError as exc:
            reason = getattr(exc, "reason", None)
            if isinstance(reason, TimeoutError | socket.timeout):
                raise GenieAcsTimeout("GenieACS request timed out") from exc
            raise GenieAcsTransportError(f"GenieACS request failed: {reason}") from exc
        except ssl.SSLError as exc:
            raise GenieAcsTransportError(f"GenieACS TLS request failed: {exc}") from exc


class GenieAcsNbiClient:
    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 10.0,
        verify_tls: bool = True,
        ca_bundle: Path | None = None,
        username: str = "",
        password: str = "",
        token: str = "",
        extra_headers: Mapping[str, str] | None = None,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        transport: HttpTransport | None = None,
    ) -> None:
        self._base_url = _base_url(base_url)
        self._timeout_seconds = timeout_seconds
        self._verify_tls = verify_tls
        self._ca_bundle = ca_bundle
        self._username = username
        self._password = password
        self._token = token
        self._extra_headers = dict(extra_headers or {})
        self._max_response_bytes = max_response_bytes
        self._transport = transport or StdlibHttpTransport()

    @classmethod
    def from_settings(
        cls,
        settings: Any,
        *,
        transport: HttpTransport | None = None,
    ) -> "GenieAcsNbiClient":
        return cls(
            base_url=settings.url,
            timeout_seconds=settings.timeout_seconds,
            verify_tls=settings.verify_tls,
            ca_bundle=settings.ca_bundle,
            username=settings.username,
            password=settings.password,
            token=settings.token,
            max_response_bytes=settings.max_response_bytes,
            transport=transport,
        )

    def __repr__(self) -> str:
        auth = "token" if self._token else "basic" if self._username or self._password else "none"
        return (
            f"GenieAcsNbiClient(base_url={self._base_url!r}, "
            f"timeout_seconds={self._timeout_seconds!r}, verify_tls={self._verify_tls!r}, "
            f"auth={auth!r})"
        )

    def query_devices(
        self,
        *,
        query: Mapping[str, Any] | None = None,
        projection: Sequence[str] = (),
    ) -> tuple[Mapping[str, Any], ...]:
        params: dict[str, str] = {}
        if query is not None:
            params["query"] = _compact_json(query)
        if projection:
            params["projection"] = ",".join(projection)
        payload = self._request_json("GET", "/devices", query=params, expected=(200,))
        if not isinstance(payload, list):
            raise GenieAcsUnexpectedResponse("GET /devices must return a JSON list")
        devices: list[Mapping[str, Any]] = []
        for item in payload:
            if not isinstance(item, Mapping):
                raise GenieAcsUnexpectedResponse("GET /devices returned a non-object item")
            devices.append(item)
        return tuple(devices)

    def query_device(
        self,
        device_id: str,
        *,
        projection: Sequence[str] = (),
    ) -> Mapping[str, Any] | None:
        devices = self.query_devices(query={"_id": device_id}, projection=projection)
        if len(devices) > 1:
            raise GenieAcsUnexpectedResponse(f"GenieACS returned {len(devices)} devices for one _id")
        return devices[0] if devices else None

    def post_task(
        self,
        device_id: str,
        task: Mapping[str, Any],
        *,
        connection_request: bool = False,
    ) -> GenieAcsTaskResult:
        _validate_device_id(device_id)
        if not isinstance(task.get("name"), str) or not task["name"]:
            raise ValueError("GenieACS task requires a non-empty name")
        flags = ("connection_request",) if connection_request else ()
        response = self._request_json_response(
            "POST",
            f"/devices/{quote(device_id, safe='')}/tasks",
            query_flags=flags,
            body=task,
            expected=(200, 202),
            allow_empty=True,
        )
        faults = _faults(response.payload)
        state = GenieAcsTaskState.QUEUED if response.status_code == 202 else GenieAcsTaskState.EXECUTED
        if faults:
            state = GenieAcsTaskState.FAILED
        return GenieAcsTaskResult(
            state=state,
            status_code=response.status_code,
            payload=response.payload,
            task_id=_task_id(response.payload),
            faults=faults,
        )

    def refresh_object(
        self,
        device_id: str,
        object_name: str,
        *,
        connection_request: bool = False,
    ) -> GenieAcsTaskResult:
        _validate_parameter_path(object_name, allow_object=True)
        return self.post_task(
            device_id,
            {"name": "refreshObject", "objectName": object_name},
            connection_request=connection_request,
        )

    def get_parameter_values(
        self,
        device_id: str,
        parameter_names: Sequence[str],
        *,
        connection_request: bool = False,
    ) -> GenieAcsTaskResult:
        names = tuple(parameter_names)
        if not names:
            raise ValueError("getParameterValues requires at least one parameter")
        for name in names:
            _validate_parameter_path(name)
        return self.post_task(
            device_id,
            {"name": "getParameterValues", "parameterNames": list(names)},
            connection_request=connection_request,
        )

    def set_parameter_values(
        self,
        device_id: str,
        parameter_values: Sequence[Sequence[Any]],
        *,
        connection_request: bool = False,
    ) -> GenieAcsTaskResult:
        values: list[list[Any]] = []
        for value in parameter_values:
            if len(value) != 3:
                raise ValueError("setParameterValues entries must be [path, value, xsd_type]")
            path, raw_value, value_type = value
            _validate_parameter_path(str(path))
            if not isinstance(value_type, str) or not value_type:
                raise ValueError("setParameterValues entries require an xsd type")
            values.append([str(path), raw_value, value_type])
        if not values:
            raise ValueError("setParameterValues requires at least one parameter")
        return self.post_task(
            device_id,
            {"name": "setParameterValues", "parameterValues": values},
            connection_request=connection_request,
        )

    def add_object(
        self,
        device_id: str,
        object_name: str,
        *,
        connection_request: bool = False,
    ) -> GenieAcsTaskResult:
        _validate_parameter_path(object_name, allow_object=True)
        return self.post_task(
            device_id,
            {"name": "addObject", "objectName": object_name},
            connection_request=connection_request,
        )

    def delete_object(
        self,
        device_id: str,
        object_name: str,
        *,
        connection_request: bool = False,
    ) -> GenieAcsTaskResult:
        _validate_parameter_path(object_name, allow_object=True)
        return self.post_task(
            device_id,
            {"name": "deleteObject", "objectName": object_name},
            connection_request=connection_request,
        )

    def get_tasks(
        self,
        *,
        query: Mapping[str, Any] | None = None,
    ) -> tuple[Mapping[str, Any], ...]:
        params: dict[str, str] = {}
        if query is not None:
            params["query"] = _compact_json(query)
        payload = self._request_json("GET", "/tasks", query=params, expected=(200,))
        if not isinstance(payload, list):
            raise GenieAcsUnexpectedResponse("GET /tasks must return a JSON list")
        tasks: list[Mapping[str, Any]] = []
        for item in payload:
            if not isinstance(item, Mapping):
                raise GenieAcsUnexpectedResponse("GET /tasks returned a non-object item")
            tasks.append(item)
        return tuple(tasks)

    def delete_task(self, task_id: str) -> None:
        if not task_id or any(ord(char) < 32 for char in task_id):
            raise ValueError("invalid GenieACS task id")
        self._request_json_response(
            "DELETE",
            f"/tasks/{quote(task_id, safe='')}",
            expected=(200, 202, 204),
            allow_empty=True,
        )

    def redacted_default_headers(self) -> Mapping[str, str]:
        return redact_headers(self._headers())

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, str] | None = None,
        expected: tuple[int, ...],
    ) -> Any:
        return self._request_json_response(
            method,
            path,
            query=query,
            expected=expected,
        ).payload

    def _request_json_response(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, str] | None = None,
        query_flags: Sequence[str] = (),
        body: Mapping[str, Any] | None = None,
        expected: tuple[int, ...],
        allow_empty: bool = False,
    ) -> "_JsonResponse":
        request = HttpRequest(
            method=method,
            url=self._url(path, query=query, query_flags=query_flags),
            headers=self._headers(has_body=body is not None),
            body=(
                json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
                if body is not None
                else None
            ),
            timeout_seconds=self._timeout_seconds,
            verify_tls=self._verify_tls,
            ca_bundle=self._ca_bundle,
            max_response_bytes=self._max_response_bytes,
        )
        response = self._transport.request(request)
        if len(response.body) > self._max_response_bytes:
            raise GenieAcsResponseTooLarge("GenieACS response exceeded configured byte limit")
        if response.status_code not in expected:
            raise GenieAcsHttpError(response.status_code, method=method, path=path, body=response.body)
        if not response.body.strip():
            if allow_empty:
                return _JsonResponse(response.status_code, None, response.headers)
            raise GenieAcsUnexpectedResponse(f"GenieACS {method} {path} returned an empty body")
        try:
            payload = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GenieAcsJsonError(f"GenieACS {method} {path} returned invalid JSON") from exc
        return _JsonResponse(response.status_code, payload, response.headers)

    def _headers(self, *, has_body: bool = False) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "open-omada-device-agent/genieacs",
        }
        if has_body:
            headers["Content-Type"] = "application/json"
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        elif self._username or self._password:
            raw = f"{self._username}:{self._password}".encode("utf-8")
            headers["Authorization"] = f"Basic {base64.b64encode(raw).decode('ascii')}"
        headers.update(self._extra_headers)
        return headers

    def _url(
        self,
        path: str,
        *,
        query: Mapping[str, str] | None = None,
        query_flags: Sequence[str] = (),
    ) -> str:
        suffix = path if path.startswith("/") else f"/{path}"
        raw_parts: list[str] = []
        if query:
            raw_parts.append(urlencode(query))
        raw_parts.extend(quote(flag, safe="") for flag in query_flags)
        query_string = "&".join(raw_parts)
        return f"{self._base_url}{suffix}" + (f"?{query_string}" if query_string else "")


@dataclass(frozen=True)
class _JsonResponse:
    status_code: int
    payload: Any
    headers: Mapping[str, str]


def redact_headers(headers: Mapping[str, str]) -> dict[str, str]:
    redacted: dict[str, str] = {}
    for name, value in headers.items():
        if name.lower() == "authorization":
            redacted[name] = "<redacted>"
        else:
            redacted[name] = value
    return redacted


def _base_url(raw: str) -> str:
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("GenieACS base URL must be http(s)")
    return raw.rstrip("/")


def _compact_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def _ssl_context(verify_tls: bool, ca_bundle: Path | None) -> ssl.SSLContext | None:
    if verify_tls:
        return ssl.create_default_context(cafile=str(ca_bundle) if ca_bundle is not None else None)
    return ssl._create_unverified_context()


def _read_bounded(stream: Any, max_bytes: int) -> bytes:
    body = stream.read(max_bytes + 1)
    if len(body) > max_bytes:
        raise GenieAcsResponseTooLarge("GenieACS response exceeded configured byte limit")
    return body


def _validate_device_id(device_id: str) -> None:
    if not device_id or any(ord(char) < 32 for char in device_id):
        raise ValueError("invalid GenieACS device id")


def _validate_parameter_path(path: str, *, allow_object: bool = False) -> None:
    if not path or any(ord(char) < 32 for char in path):
        raise ValueError("invalid TR-069 parameter path")
    if " " in path or ".." in path or path.startswith("."):
        raise ValueError("invalid TR-069 parameter path")
    if not allow_object and path.endswith("."):
        raise ValueError("parameter path must not end with '.'")


def _task_id(payload: Any) -> str | None:
    if isinstance(payload, Mapping):
        for key in ("_id", "id", "taskId"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def _faults(payload: Any) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(payload, Mapping):
        return ()
    raw = payload.get("faults") or payload.get("fault")
    if isinstance(raw, Mapping):
        return (raw,)
    if isinstance(raw, list):
        return tuple(item for item in raw if isinstance(item, Mapping))
    return ()


def _body_preview(body: bytes, *, limit: int = 200) -> str:
    return body[:limit].decode("utf-8", errors="replace")
