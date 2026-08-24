"""ECSP V2 adoption, managed reconnect, configuration ACKs and informs."""
from __future__ import annotations

import json
import ssl
import logging
import socket
import time
import uuid
from dataclasses import dataclass
from typing import Any

from . import config
from .ap_config import parse_set_request
from .capabilities import ap_components_v2
from .crypto import calculate_md5_mode_auth
from .domain import AccessPointConfigUpdate
from .ecsp import (
    CipherType,
    MessageType,
    build_message,
    message_type_name,
    recv_tcp_message,
    send_tcp_message,
)
from .identity import controller_setting, device_info, device_misc
from .session_state import save_state

log = logging.getLogger("open_omada.adoption")


class AuthenticationRejected(RuntimeError):
    """Controller rejected the Device Account credentials for this attempt."""


@dataclass
class AdoptionResult:
    reached_system_verify: bool = False
    controller_id: str = ""
    username: str = ""


def _log_message(direction: str, message: dict[str, Any], *, dump_json: bool) -> None:
    header = message.get("header") or {}
    msg_type = int(header.get("type", -1))
    log.info(
        "%s %s type=%s seq=%s error=%s",
        direction,
        message_type_name(msg_type),
        msg_type,
        header.get("seq"),
        header.get("error", 0),
    )
    if dump_json:
        log.info(
            "%s JSON %s",
            direction,
            json.dumps(message, ensure_ascii=False, separators=(",", ":")),
        )


def _recv_until(sock: socket.socket, expected: MessageType, *, dump_json: bool) -> dict[str, Any]:
    while True:
        message, _ = recv_tcp_message(sock)
        _log_message("RX/TCP", message, dump_json=dump_json)
        header = message.get("header") or {}
        msg_type = int(header.get("type", -1))
        if msg_type == int(expected):
            return message
        log.warning(
            "Expected %s but controller sent %s first; keeping the session open.",
            expected.name,
            message_type_name(msg_type),
        )


def _preconnect_body(controller_id: str, *, managed_reconnect: bool = False) -> dict[str, Any]:
    # Controller 6.2's V2 PRE_CONNECT parser explicitly classifies rebuild=1
    # as an already-managed reconnect. rebuild=0 + controllerSetting is the
    # pre-link/adoption path; using that shape after a restart makes
    # manager-core look for transient adopt state and the server closes the
    # manage socket when none exists.
    info = dict(device_info())
    if managed_reconnect:
        info["isFactory"] = False

    return {
        "needUsername": True,
        "rebuild": 1 if managed_reconnect else 0,
        "secureCap": 0,
        "deviceInfo": info,
        "deviceMisc": device_misc(),
        # rebuild=1 wins the mode classification. Keeping controllerSetting on
        # reconnect also lets manager-core reconstruct controller routing if a
        # MAC -> Omadac mapping is temporarily absent.
        "controllerSetting": controller_setting(controller_id),
    }


def _device_negotiation_body(
    controller_id: str, *, config_version: int = 0
) -> dict[str, Any]:
    """Build the minimal AP V2 adoption response accepted by manager-core.

    ``devCap`` and ``components_v2`` must be objects, not null.  More
    importantly, ``components_v2`` must contain at least one controller-known
    component: an empty map is accepted on the wire but manager-core later
    marks the rebuilt component image invalid/incompatible.

    ``configVersion`` must also be present or the adoption handler stops before
    SYSTEM_NEGOTIATION. Initial adoption reports 0 to request a full sync, while
    managed reconnects report the last persisted version so Controller does not
    unnecessarily provision the same full configuration again.
    """
    adopt_info = dict(device_info())
    # These are discovery-only fields.  ApAdoptDeviceInfoV2 stores unknown
    # members, but omitting them makes the negotiation payload match its DTO.
    adopt_info.pop("ip", None)
    adopt_info.pop("isFactory", None)

    return {
        "configVersion": int(config_version),
        "devCap": {},
        "deviceInfo": adopt_info,
        "controllerSetting": {"controllerId": controller_id},
        "components": {},
        "components_v2": ap_components_v2(),
        "channelInfo": [],
        "radioCap": [],
        "deviceMisc": device_misc(),
    }


def _inform_body(*, need_reply: bool, started_at: float) -> dict[str, Any]:
    """Build the minimal periodic AP inform used after initial sync.

    Controller 6.2.14.11 advertises ``informInterval.base=3`` and
    ``informInterval.deviceInfo=3`` during SYSTEM_NEGOTIATION.  A real managed
    AP therefore starts reporting device information immediately after the
    adoption handshake instead of leaving the manage socket completely idle.

    ``EapInformDeviceInfo`` accepts additional JSON properties, so reusing the
    discovery identity is safe.  The two semantic changes below are important:
    the device is no longer factory-new after adoption and uptime now advances.
    """
    info = dict(device_info())
    info["isFactory"] = False
    info["upTime"] = str(max(0, int(time.monotonic() - started_at)))
    return {
        "needReply": 1 if need_reply else 0,
        "deviceInfo": info,
        # Wired APs are expected to report lanInfo.  Without it Controller 6.2
        # keeps warning "Missing lan info for wired ap" and cannot populate
        # the uplink details used by topology/health views.  LanInfo.rate is a
        # numeric string in manager-message and is parsed with Double.parseDouble.
        "lanInfo": {
            "rate": str(config.LAN_RATE),
            "duplex": int(config.LAN_DUPLEX),
            "port": config.LAN_PORT,
        },
    }


def _set_response_body(
    request: dict[str, Any], *, current_config_version: int | None = None
) -> dict[str, Any]:
    """Build the ECSP V2 BaseConfigResponse for a SET_REQUEST.

    Controller uses two valid versioning forms in ``BaseConfigBody``:

    * ``configVersion`` for a full/absolute configuration;
    * ``configVersionInc`` for an incremental setting change.

    The latter is what Controller 6.2 sends for small live changes such as the
    AP locate LED.  The request does not contain the resulting absolute version,
    so the device derives it from the version it has already applied.
    """
    body = request.get("body") or {}
    if not isinstance(body, dict):
        raise RuntimeError("SET_REQUEST body is not an object")

    sequence_id = body.get("sequenceId")
    if sequence_id is None:
        raise RuntimeError(
            "SET_REQUEST is missing sequenceId; refusing to ACK an uncorrelated config"
        )

    absolute_version = body.get("configVersion")
    version_inc = body.get("configVersionInc")

    if absolute_version is not None:
        applied_version = int(absolute_version)
    elif version_inc is not None:
        if current_config_version is None:
            raise RuntimeError(
                "SET_REQUEST uses configVersionInc but the local config version is unknown"
            )
        increment = int(version_inc)
        if increment < 0:
            raise RuntimeError(
                f"SET_REQUEST has invalid negative configVersionInc={increment}"
            )
        applied_version = int(current_config_version) + increment
    else:
        raise RuntimeError(
            "SET_REQUEST has neither configVersion nor configVersionInc"
        )

    return {
        "sequenceId": int(sequence_id),
        "errcode": 0,
        "configVersion": applied_version,
    }


def _describe_config_update(update: AccessPointConfigUpdate) -> str:
    parts = [
        f"sequenceId={update.sequence_id}",
        f"configVersion={update.config_version}",
        f"configVersionInc={update.config_version_inc}",
    ]
    if update.radios:
        bands = ",".join(sorted(radio.band.value for radio in update.radios))
        parts.append(f"radios={len(update.radios)}[{bands}]")
    if update.wlans:
        bands = ",".join(sorted(wlan.band.value for wlan in update.wlans))
        parts.append(f"wlans={len(update.wlans)}[{bands}]")
    if update.management_vlan is not None:
        parts.append(
            "managementVlan="
            f"{'on' if update.management_vlan.enabled else 'off'}:"
            f"{update.management_vlan.vlan_id}"
        )
    if update.portal_free_policy is not None:
        parts.append(
            "portalFreePolicy="
            f"l2:{len(update.portal_free_policy.layer2_rules)},"
            f"url:{len(update.portal_free_policy.url_rules)}"
        )
    if update.unhandled_keys:
        parts.append(f"unhandled={','.join(update.unhandled_keys)}")
    return " ".join(parts)


def _send_set_response(
    sock: socket.socket,
    request: dict[str, Any],
    *,
    controller_id: str,
    current_config_version: int | None,
    dump_json: bool,
) -> tuple[int, int]:
    """Acknowledge a controller SET_REQUEST and return version/sequence."""
    request_header = request.get("header") or {}
    try:
        update = parse_set_request(request)
        log.info("Parsed AP SET_REQUEST domains: %s", _describe_config_update(update))
    except ValueError as exc:
        # Keep the current conservative behavior: until the adapter/reconciler
        # is enabled, malformed AP subdocuments are logged but the envelope ACK
        # path still follows BaseConfigResponse so existing adoption labs keep
        # working. The apply phase will convert validation failures into device
        # config errors once those components are advertised.
        log.warning("Could not parse AP config domains in SET_REQUEST: %s", exc)
    response_body = _set_response_body(
        request, current_config_version=current_config_version
    )
    response = build_message(
        mac=config.MAC,
        msg_type=MessageType.SET_RESPONSE,
        body=response_body,
        version=config.ECSP_VERSION,
        ver_cap=config.ECSP_VER_CAP,
        # Request/response correlation uses the ECSP header seq, exactly as
        # INFORM_RESPONSE mirrors INFORM_REQUEST.seq.
        seq=request_header.get("seq"),
        dest=controller_id,
        timestamp=int(time.time() * 1000),
        error=0,
    )
    send_tcp_message(sock, response)
    _log_message("TX/TCP", response, dump_json=dump_json)
    return int(response_body["configVersion"]), int(response_body["sequenceId"])


def _send_inform(
    sock: socket.socket,
    *,
    seq: int,
    controller_id: str,
    started_at: float,
    need_reply: bool,
    dump_json: bool,
) -> None:
    inform = build_message(
        mac=config.MAC,
        msg_type=MessageType.INFORM_REQUEST,
        body=_inform_body(need_reply=need_reply, started_at=started_at),
        version=config.ECSP_VERSION,
        ver_cap=config.ECSP_VER_CAP,
        seq=seq,
        dest=controller_id,
        timestamp=int(time.time() * 1000),
    )
    send_tcp_message(sock, inform)
    _log_message("TX/TCP", inform, dump_json=dump_json)


def run_v2_adoption(
    *,
    controller_host: str,
    adopt_port: int,
    controller_id: str,
    dump_json: bool = False,
    managed_reconnect: bool = False,
    known_config_version: int | None = None,
) -> AdoptionResult:
    if not controller_id:
        raise RuntimeError(
            "PRE_ADOPT_REQUEST did not provide header.dest and OMADA_CONTROLLER_ID is empty"
        )

    log.info(
        "Opening V2 %s TCP session to %s:%d",
        "managed-reconnect" if managed_reconnect else "manage/adopt",
        controller_host,
        adopt_port,
    )
    raw_sock = socket.create_connection(
        (controller_host, adopt_port),
        timeout=config.TCP_TIMEOUT,
    )

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.maximum_version = ssl.TLSVersion.TLSv1_2

    if config.TLS_VERIFY:
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
        if config.TLS_CA_FILE:
            ctx.load_verify_locations(cafile=config.TLS_CA_FILE)
        else:
            ctx.load_default_certs()
    else:
        # Omada device-management endpoints commonly use private/self-signed
        # certificates. Verification is therefore operator-controlled.
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    sock = ctx.wrap_socket(
        raw_sock,
        server_hostname=controller_host,
    )
    sock.settimeout(config.TCP_TIMEOUT)

    seq = 1
    started_at = time.monotonic()
    managed_ready = False
    try:
        preconnect = build_message(
            mac=config.MAC,
            msg_type=MessageType.PRE_CONNECT_INFO,
            body=_preconnect_body(controller_id, managed_reconnect=managed_reconnect),
            version=config.ECSP_VERSION,
            ver_cap=config.ECSP_VER_CAP,
            seq=seq,
            dest=controller_id,
            timestamp=int(time.time() * 1000),
        )
        send_tcp_message(sock, preconnect)
        _log_message("TX/TCP", preconnect, dump_json=dump_json)

        response = _recv_until(sock, MessageType.PRE_CONNECT_INFO_RESPONSE, dump_json=dump_json)
        response_header = response.get("header") or {}
        if int(response_header.get("error", 0)) != 0:
            raise RuntimeError(
                f"controller rejected PRE_CONNECT_INFO: error={response_header.get('error')}"
            )
        body = response.get("body") or {}
        random_device_key = body.get("randomKeyForDeviceVerify")
        if not isinstance(random_device_key, str) or len(random_device_key) < 36:
            raise RuntimeError(
                "PRE_CONNECT_INFO_RESPONSE has no usable randomKeyForDeviceVerify"
            )

        username = config.DEVICE_USERNAME or body.get("username") or ""
        if not username:
            raise RuntimeError(
                "controller did not return a username; set OMADA_DEVICE_USERNAME to the site's Device Account username"
            )
        if not config.DEVICE_PASSWORD:
            raise RuntimeError(
                "PRE_CONNECT succeeded, but OMADA_DEVICE_PASSWORD is empty. "
                "Set it locally to the site's Device Account password and retry adoption."
            )
        if config.DEVICE_CIPHER_TYPE != int(CipherType.MD5):
            raise RuntimeError(
                "this implementation currently supports only the verified legacy MD5 branch (OMADA_DEVICE_CIPHER_TYPE=5)"
            )

        random_system_key = str(uuid.uuid4())
        device_auth = calculate_md5_mode_auth(username, config.DEVICE_PASSWORD, random_device_key)
        seq += 1
        verify = build_message(
            mac=config.MAC,
            msg_type=MessageType.DEVICE_VERIFY_INFO,
            body={
                "auth": device_auth,
                "randomKeyForSystemVerify": random_system_key,
                "cipherType": int(CipherType.MD5),
            },
            version=config.ECSP_VERSION,
            ver_cap=config.ECSP_VER_CAP,
            seq=seq,
            dest=controller_id,
            timestamp=int(time.time() * 1000),
        )
        send_tcp_message(sock, verify)
        _log_message("TX/TCP", verify, dump_json=dump_json)

        verify_response = _recv_until(sock, MessageType.DEVICE_VERIFY_RESPONSE, dump_json=dump_json)
        verify_header = verify_response.get("header") or {}
        verify_error = int(verify_header.get("error", 0))
        if verify_error != 0:
            raise AuthenticationRejected(
                f"controller rejected DEVICE_VERIFY_INFO: error={verify_error}. "
                "The Device Account username/password most likely do not match."
            )

        verify_body = verify_response.get("body") or {}
        controller_auth = verify_body.get("auth")
        expected_controller_auth = calculate_md5_mode_auth(
            username, config.DEVICE_PASSWORD, random_system_key
        )
        if not isinstance(controller_auth, str):
            raise RuntimeError("DEVICE_VERIFY_RESPONSE succeeded but contains no legacy auth")
        if controller_auth.upper() != expected_controller_auth.upper():
            raise RuntimeError(
                "controller system-auth did not verify; refusing to mark SYSTEM_VERIFY_RESULT success"
            )
        log.info("Mutual legacy ECSP authentication verified for username=%r", username)

        seq += 1
        system_result = build_message(
            mac=config.MAC,
            msg_type=MessageType.SYSTEM_VERIFY_RESULT,
            body={},
            version=config.ECSP_VERSION,
            ver_cap=config.ECSP_VER_CAP,
            seq=seq,
            dest=controller_id,
            timestamp=int(time.time() * 1000),
            error=0,
        )
        send_tcp_message(sock, system_result)
        _log_message("TX/TCP", system_result, dump_json=dump_json)

        verify_ack = _recv_until(sock, MessageType.VERIFY_RESULT_ACK, dump_json=dump_json)
        verify_ack_error = int((verify_ack.get("header") or {}).get("error", 0))
        if verify_ack_error != 0:
            raise RuntimeError(
                f"controller rejected SYSTEM_VERIFY_RESULT: error={verify_ack_error}"
            )
        log.info("VERIFY_RESULT_ACK accepted; starting AP capability negotiation")

        seq += 1
        negotiation_config_version = (
            int(known_config_version)
            if managed_reconnect and known_config_version is not None
            else 0
        )
        negotiation_body = _device_negotiation_body(
            controller_id, config_version=negotiation_config_version
        )
        log.info(
            "Advertising %d ECSP V2 AP components at configVersion=%d: %s",
            len(negotiation_body["components_v2"]),
            negotiation_config_version,
            ",".join(sorted(negotiation_body["components_v2"])),
        )
        negotiation = build_message(
            mac=config.MAC,
            msg_type=MessageType.DEVICE_NEGOTIATION,
            body=negotiation_body,
            version=config.ECSP_VERSION,
            ver_cap=config.ECSP_VER_CAP,
            seq=seq,
            dest=controller_id,
            timestamp=int(time.time() * 1000),
        )
        send_tcp_message(sock, negotiation)
        _log_message("TX/TCP", negotiation, dump_json=dump_json)

        system_negotiation = _recv_until(
            sock, MessageType.SYSTEM_NEGOTIATION, dump_json=dump_json
        )
        system_header = system_negotiation.get("header") or {}
        system_error = int(system_header.get("error", 0))
        if system_error != 0:
            raise RuntimeError(
                f"controller rejected DEVICE_NEGOTIATION: error={system_error}"
            )

        system_body = system_negotiation.get("body")
        if isinstance(system_body, dict):
            log.info(
                "SYSTEM_NEGOTIATION accepted: configVersion=%r sequenceId=%r keys=%s",
                system_body.get("configVersion"),
                system_body.get("sequenceId"),
                ",".join(sorted(system_body.keys())),
            )
        else:
            log.warning("SYSTEM_NEGOTIATION has no object body: %r", system_body)

        seq += 1
        init_sync_result = build_message(
            mac=config.MAC,
            msg_type=MessageType.INIT_SYNC_RESULT,
            version=config.ECSP_VERSION,
            ver_cap=config.ECSP_VER_CAP,
            seq=seq,
            dest=controller_id,
            timestamp=int(time.time() * 1000),
            error=0,
            include_body=False,
        )
        send_tcp_message(sock, init_sync_result)
        _log_message("TX/TCP", init_sync_result, dump_json=dump_json)

        init_ack = _recv_until(sock, MessageType.INIT_SYNC_RESULT_ACK, dump_json=dump_json)
        init_ack_error = int((init_ack.get("header") or {}).get("error", 0))
        if init_ack_error != 0:
            raise RuntimeError(
                f"controller rejected INIT_SYNC_RESULT: error={init_ack_error}"
            )

        managed_ready = True
        log.warning(
            "INIT_SYNC_RESULT_ACK received. ECSP V2 adoption/initial-sync handshake is complete; "
            "starting managed AP informs and logging post-adoption traffic."
        )

        config_version = known_config_version if managed_reconnect else None
        sequence_id = None
        if isinstance(system_body, dict):
            if system_body.get("configVersion") is not None:
                config_version = int(system_body["configVersion"])
            if system_body.get("sequenceId") is not None:
                sequence_id = int(system_body["sequenceId"])
        saved = save_state(
            controller_id=controller_id,
            manage_port=adopt_port,
            site_id=config.SITE_ID,
            username=username,
            config_version=config_version,
            sequence_id=sequence_id,
        )
        log.info(
            "Managed reconnect state saved to %s (controller=%s:%d, mac=%s); no password is persisted",
            config.STATE_FILE,
            saved.controller_host,
            saved.manage_port,
            saved.mac,
        )

        # A real EAP begins sending informs after initial sync.  The first one
        # requests an INFORM_RESPONSE so this lab agent gets explicit evidence
        # that manager-core parsed the body.  Subsequent informs are fire-and-
        # forget and keep the server's CONNECTED context fresh.
        seq += 1
        _send_inform(
            sock,
            seq=seq,
            controller_id=controller_id,
            started_at=started_at,
            need_reply=True,
            dump_json=dump_json,
        )
        next_inform_at = time.monotonic() + max(0.5, config.INFORM_INTERVAL)

        # The next phase is the managed-device protocol (SET/GET/INFORM/NOTIFY).
        # SET_RESPONSE is now grounded in the controller's BaseConfigResponse
        # schema. GET/NOTIFY remain capture-only until we observe concrete bodies.
        sock.settimeout(0.5)
        while True:
            now = time.monotonic()
            if now >= next_inform_at:
                seq += 1
                _send_inform(
                    sock,
                    seq=seq,
                    controller_id=controller_id,
                    started_at=started_at,
                    need_reply=False,
                    dump_json=dump_json,
                )
                next_inform_at = now + max(0.5, config.INFORM_INTERVAL)

            try:
                message, _ = recv_tcp_message(sock)
            except socket.timeout:
                continue
            _log_message("RX/TCP", message, dump_json=dump_json)

            header = message.get("header") or {}
            msg_type = int(header.get("type", -1))
            if msg_type == int(MessageType.SET_REQUEST):
                applied_config_version, applied_sequence_id = _send_set_response(
                    sock,
                    message,
                    controller_id=controller_id,
                    current_config_version=config_version,
                    dump_json=dump_json,
                )
                config_version = applied_config_version
                sequence_id = applied_sequence_id
                save_state(
                    controller_id=controller_id,
                    manage_port=adopt_port,
                    site_id=config.SITE_ID,
                    username=username,
                    config_version=applied_config_version,
                    sequence_id=applied_sequence_id,
                )
                log.info(
                    "Applied controller config envelope: configVersion=%d sequenceId=%d; managed state updated",
                    applied_config_version,
                    applied_sequence_id,
                )

    except (EOFError, ConnectionError, OSError) as exc:
        log.warning("ECSP TCP session ended: %s", exc)
        return AdoptionResult(managed_ready, controller_id, locals().get("username", ""))
    finally:
        try:
            sock.close()
        except OSError:
            pass
