import base64
import json
from dataclasses import dataclass, field

import pytest

from open_omada_device_agent.adapters.outbound.genieacs.client import (
    GenieAcsHttpError,
    GenieAcsJsonError,
    GenieAcsNbiClient,
    GenieAcsResponseTooLarge,
    GenieAcsTimeout,
    HttpRequest,
    HttpResponse,
    redact_headers,
)
from open_omada_device_agent.adapters.outbound.genieacs.models import GenieAcsTaskState


@dataclass
class FakeTransport:
    responses: list[HttpResponse] = field(default_factory=list)
    error: Exception | None = None
    requests: list[HttpRequest] = field(default_factory=list)

    def request(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.responses.pop(0)


def _json_response(status_code, payload):
    return HttpResponse(
        status_code=status_code,
        headers={"content-type": "application/json"},
        body=json.dumps(payload).encode("utf-8"),
    )


def test_query_devices_uses_safe_json_query_and_projection_encoding():
    transport = FakeTransport(responses=[_json_response(200, [{"_id": "device-1"}])])
    client = GenieAcsNbiClient(
        base_url="https://acs.example.test:7557/base/",
        transport=transport,
    )

    devices = client.query_devices(
        query={"_id": "001122-Router ABC/1"},
        projection=("Device.DeviceInfo.Manufacturer", "Device.WiFi."),
    )

    assert devices == ({"_id": "device-1"},)
    request = transport.requests[0]
    assert request.method == "GET"
    assert request.url.startswith("https://acs.example.test:7557/base/devices?")
    assert "query=%7B%22_id%22%3A%22001122-Router+ABC%2F1%22%7D" in request.url
    assert "projection=Device.DeviceInfo.Manufacturer%2CDevice.WiFi." in request.url


def test_query_device_rejects_multiple_matches_for_exact_id():
    transport = FakeTransport(responses=[_json_response(200, [{"_id": "a"}, {"_id": "b"}])])
    client = GenieAcsNbiClient(base_url="http://127.0.0.1:7557", transport=transport)

    with pytest.raises(Exception, match="returned 2 devices"):
        client.query_device("same-id")


def test_post_task_encodes_device_id_and_distinguishes_executed_from_queued():
    transport = FakeTransport(
        responses=[
            _json_response(200, {"_id": "task-executed"}),
            _json_response(202, {"_id": "task-queued"}),
        ]
    )
    client = GenieAcsNbiClient(base_url="http://127.0.0.1:7557", transport=transport)

    executed = client.refresh_object(
        "001122-Router ABC/1",
        "Device.WiFi.",
        connection_request=True,
    )
    queued = client.get_parameter_values(
        "001122-Router ABC/1",
        ("Device.WiFi.Radio.1.Enable",),
    )

    assert executed.state is GenieAcsTaskState.EXECUTED
    assert executed.task_id == "task-executed"
    assert queued.state is GenieAcsTaskState.QUEUED
    assert queued.task_id == "task-queued"
    assert transport.requests[0].url == (
        "http://127.0.0.1:7557/devices/001122-Router%20ABC%2F1/tasks?connection_request"
    )
    assert json.loads(transport.requests[0].body or b"{}") == {
        "name": "refreshObject",
        "objectName": "Device.WiFi.",
    }


def test_set_parameter_values_sends_typed_entries_without_shelling_out():
    transport = FakeTransport(responses=[_json_response(200, {"_id": "task-1"})])
    client = GenieAcsNbiClient(base_url="http://127.0.0.1:7557", transport=transport)

    result = client.set_parameter_values(
        "device-id",
        (
            ("Device.WiFi.SSID.1.SSID", "Media Beach", "xsd:string"),
            ("Device.WiFi.Radio.1.Enable", True, "xsd:boolean"),
        ),
    )

    assert result.executed is True
    assert json.loads(transport.requests[0].body or b"{}") == {
        "name": "setParameterValues",
        "parameterValues": [
            ["Device.WiFi.SSID.1.SSID", "Media Beach", "xsd:string"],
            ["Device.WiFi.Radio.1.Enable", True, "xsd:boolean"],
        ],
    }


def test_task_faults_are_explicit_failures_even_when_http_was_successful():
    transport = FakeTransport(
        responses=[_json_response(200, {"_id": "task-1", "faults": [{"code": "9008"}]})]
    )
    client = GenieAcsNbiClient(base_url="http://127.0.0.1:7557", transport=transport)

    result = client.post_task("device-id", {"name": "refreshObject", "objectName": "Device."})

    assert result.failed is True
    assert result.faults == ({"code": "9008"},)


def test_delete_task_uses_encoded_task_path_and_allows_empty_204():
    transport = FakeTransport(responses=[HttpResponse(status_code=204, headers={}, body=b"")])
    client = GenieAcsNbiClient(base_url="http://127.0.0.1:7557", transport=transport)

    client.delete_task("task/id")

    assert transport.requests[0].method == "DELETE"
    assert transport.requests[0].url == "http://127.0.0.1:7557/tasks/task%2Fid"


def test_http_error_and_malformed_json_are_not_collapsed_to_success():
    http_transport = FakeTransport(responses=[HttpResponse(500, {}, b"database unavailable")])
    http_client = GenieAcsNbiClient(base_url="http://127.0.0.1:7557", transport=http_transport)

    with pytest.raises(GenieAcsHttpError, match="HTTP 500"):
        http_client.query_devices()

    json_transport = FakeTransport(responses=[HttpResponse(200, {}, b"{")])
    json_client = GenieAcsNbiClient(base_url="http://127.0.0.1:7557", transport=json_transport)

    with pytest.raises(GenieAcsJsonError):
        json_client.query_devices()


def test_timeout_and_large_response_are_explicit_failures():
    timeout_client = GenieAcsNbiClient(
        base_url="http://127.0.0.1:7557",
        transport=FakeTransport(error=GenieAcsTimeout("timed out")),
    )

    with pytest.raises(GenieAcsTimeout):
        timeout_client.query_devices()

    large_client = GenieAcsNbiClient(
        base_url="http://127.0.0.1:7557",
        transport=FakeTransport(responses=[HttpResponse(200, {}, b"[{}]")]),
        max_response_bytes=3,
    )

    with pytest.raises(GenieAcsResponseTooLarge):
        large_client.query_devices()


def test_authorization_headers_are_redacted_and_client_repr_is_secret_free():
    client = GenieAcsNbiClient(
        base_url="https://acs.example.test:7557",
        username="operator",
        password="do-not-log-this-password",
        token="do-not-log-this-token",
    )

    headers = client.redacted_default_headers()
    rendered = repr(client)

    assert headers["Authorization"] == "<redacted>"
    assert "do-not-log-this-password" not in rendered
    assert "do-not-log-this-token" not in rendered
    assert "do-not-log-this-token" not in str(headers)


def test_basic_auth_is_available_when_no_token_is_configured():
    transport = FakeTransport(responses=[_json_response(200, [])])
    client = GenieAcsNbiClient(
        base_url="https://acs.example.test:7557",
        username="operator",
        password="password",
        transport=transport,
    )

    client.query_devices()

    expected = base64.b64encode(b"operator:password").decode("ascii")
    assert transport.requests[0].headers["Authorization"] == f"Basic {expected}"
    assert redact_headers(transport.requests[0].headers)["Authorization"] == "<redacted>"
