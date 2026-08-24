"""Proactive ECSP discovery plus resilient adoption/reconnect supervision."""
from __future__ import annotations

import json
import logging
import socket
import time
from typing import Any

from . import config
from .adoption import AuthenticationRejected, run_v2_adoption
from .contexts.lifecycle.application import ManagedSessionServices
from .adapters.inbound.ecsp.protocol import (
    MAX_DISCOVERY_PAYLOAD,
    MessageType,
    build_message,
    decode_frame,
    encode_frame,
    message_type_name,
    normalize_mac,
)
from .identity import controller_setting, device_info, device_misc

log = logging.getLogger("open_omada.discovery")


def build_discovery(
    seq: int,
    controller_id: str = "",
    destination_id: str = "",
    *,
    managed_restart: bool = False,
) -> dict[str, Any]:
    info = dict(device_info())
    if managed_restart:
        # On restart an already-adopted AP must not present itself as factory-new.
        # Controller uses this together with its persistent device record to
        # rebuild/refresh the device image before the manage TCP link returns.
        info["isFactory"] = False
    body = {
        "deviceInfo": info,
        "deviceMisc": device_misc(),
        "controllerSetting": controller_setting(controller_id, destination_id),
    }
    return build_message(
        mac=config.MAC,
        msg_type=MessageType.DISCOVERY,
        body=body,
        version=config.ECSP_VERSION,
        ver_cap=config.ECSP_VER_CAP,
        seq=seq,
        dest=destination_id or controller_id or None,
        timestamp=int(time.time() * 1000),
    )


def log_inbound(
    message: dict[str, Any], addr: tuple[str, int], *, dump_json: bool = False
) -> None:
    header = message.get("header") or {}
    msg_type = int(header.get("type", -1))
    log.info(
        "RX %s type=%s seq=%s from %s:%s",
        message_type_name(msg_type),
        msg_type,
        header.get("seq"),
        addr[0],
        addr[1],
    )
    if dump_json:
        log.info("RX JSON %s", json.dumps(message, ensure_ascii=False, separators=(",", ":")))


def _retry_delay() -> float:
    return max(0.5, config.RECONNECT_DELAY)


def _run_saved_managed_session(*, dump_tx: bool, services: ManagedSessionServices) -> bool:
    """Reconnect an already-adopted device.

    Returns False when several consecutive attempts die before initial sync.
    That pattern means the controller-side ECSP context/adopt-info is stale or
    missing, so hammering TCP/29814 cannot repair it.  The caller then falls
    back to a managed rediscovery cycle, which rehydrates the controller's
    device image/context without discarding our local non-secret state.
    """
    pre_sync_failures = 0
    max_failures = max(1, int(config.MANAGED_RECONNECT_ATTEMPTS))

    while True:
        state = services.state_repository.load()
        if state is None:
            return False

        log.warning(
            "Managed state found: reconnecting %s directly to %s:%d without a new Adopt click",
            state.mac,
            state.controller_host,
            state.manage_port,
        )
        try:
            result = run_v2_adoption(
                services=services,
                controller_host=state.controller_host,
                adopt_port=state.manage_port,
                controller_id=state.controller_id,
                dump_json=dump_tx,
                managed_reconnect=True,
                known_config_version=state.config_version,
            )
            if result.reached_system_verify:
                pre_sync_failures = 0
                log.warning(
                    "Managed ECSP session ended after successful sync; reconnecting in %.1fs",
                    _retry_delay(),
                )
            else:
                pre_sync_failures += 1
                log.warning(
                    "Managed ECSP reconnect ended before initial sync (%d/%d)",
                    pre_sync_failures,
                    max_failures,
                )
        except AuthenticationRejected as exc:
            # Bad credentials are recoverable and should not throw away a good
            # controller/device mapping. Keep retrying the same managed path.
            pre_sync_failures = 0
            log.error(
                "Device Account authentication rejected: %s Agent stays alive and will retry in %.1fs.",
                exc,
                _retry_delay(),
            )
        except RuntimeError as exc:
            pre_sync_failures += 1
            log.error(
                "Managed reconnect was rejected by the controller (%d/%d): %s",
                pre_sync_failures,
                max_failures,
                exc,
            )
        except (EOFError, ConnectionError, OSError) as exc:
            pre_sync_failures += 1
            log.warning(
                "Managed reconnect transport failed before sync (%d/%d): %s",
                pre_sync_failures,
                max_failures,
                exc,
            )

        if pre_sync_failures >= max_failures:
            log.warning(
                "Direct managed reconnect failed %d times before initial sync; "
                "switching to managed rediscovery to rebuild controller-side ECSP state",
                pre_sync_failures,
            )
            return False

        time.sleep(_retry_delay())


def _try_bootstrap_managed_reconnect(*, dump_tx: bool, services: ManagedSessionServices) -> bool:
    """Upgrade path for devices adopted before local reconnect state existed."""
    if not config.CONTROLLER_ID:
        return False

    log.info(
        "No persisted managed state; trying direct reconnect bootstrap to %s:%d before discovery",
        config.CONTROLLER_HOST,
        config.MANAGE_PORT,
    )
    for auth_attempt in range(1, 4):
        try:
            result = run_v2_adoption(
                services=services,
                controller_host=config.CONTROLLER_HOST,
                adopt_port=config.MANAGE_PORT,
                controller_id=config.CONTROLLER_ID,
                dump_json=dump_tx,
                managed_reconnect=True,
            )
            if services.state_repository.load() is not None:
                return True
            if result.reached_system_verify:
                log.warning(
                    "Bootstrap reconnect synced but no managed state was saved; falling back to discovery"
                )
            return False
        except AuthenticationRejected as exc:
            log.error(
                "Bootstrap managed reconnect authentication rejected (%d/3): %s",
                auth_attempt,
                exc,
            )
            if auth_attempt < 3:
                log.info(
                    "Retrying bootstrap authentication in %.1fs without exiting",
                    _retry_delay(),
                )
                time.sleep(_retry_delay())
            else:
                log.warning(
                    "Bootstrap credentials were rejected 3 times; falling back to discovery"
                )
        except (EOFError, ConnectionError, OSError, RuntimeError) as exc:
            log.info(
                "Bootstrap managed reconnect unavailable (%s); falling back to discovery",
                exc,
            )
            return False
    return False


def run(
    *,
    services: ManagedSessionServices,
    once: bool = False,
    dump_tx: bool = False,
    no_adopt: bool = False,
    force_discovery: bool = False,
) -> None:
    # Once initial sync has completed, only non-secret routing state is stored.
    # Normal restarts therefore skip discovery/adoption and reconnect directly
    # to the V2 manage port like an already-managed EAP.
    saved_state = services.state_repository.load()
    managed_recovery = False
    if not force_discovery and not no_adopt and not once and saved_state is not None:
        if _run_saved_managed_session(dump_tx=dump_tx, services=services):
            return
        # The controller closed PRE_CONNECT before it could reply repeatedly.
        # Keep the state file and re-advertise the same adopted MAC/site over
        # UDP so manager-core can reconstruct its device image/context.
        managed_recovery = True
        saved_state = services.state_repository.load()

    # Older agent versions did not persist state. Try the ordinary managed
    # reconnect path once before discovery so an already-adopted AP can upgrade
    # without one final manual Adopt click.
    if not managed_recovery and not force_discovery and not no_adopt and not once:
        if _try_bootstrap_managed_reconnect(dump_tx=dump_tx, services=services):
            _run_saved_managed_session(dump_tx=dump_tx, services=services)
            return

    target = (config.CONTROLLER_HOST, config.DISCOVERY_PORT)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", config.LOCAL_DISCOVERY_PORT))
    sock.settimeout(0.5)
    local = sock.getsockname()
    log.info("UDP socket bound at %s:%s; controller=%s:%s", local[0], local[1], *target)

    seq = 1
    next_send = 0.0
    deadline: float | None = None
    next_managed_probe_at = (
        time.monotonic() + 1.5 if managed_recovery else float("inf")
    )
    controller_id = (saved_state.controller_id if managed_recovery and saved_state else config.CONTROLLER_ID)
    destination_id = (
        saved_state.site_id
        if managed_recovery and saved_state and saved_state.site_id
        else config.SITE_ID or config.DEST_OMADAC_ID or controller_id
    )
    if managed_recovery:
        log.warning(
            "Managed rediscovery active for %s: advertising isFactory=false to %s:%d "
            "and waiting for controller re-link/PRE_ADOPT",
            saved_state.mac if saved_state else config.MAC,
            target[0],
            target[1],
        )
    if config.SITE_ID or (managed_recovery and saved_state and saved_state.site_id):
        log.info(
            "Site-scoped discovery enabled: siteId=%s controllerId=%s",
            destination_id,
            controller_id or "<empty>",
        )

    try:
        while True:
            now = time.monotonic()
            if now >= next_send:
                message = build_discovery(
                    seq,
                    controller_id,
                    destination_id,
                    managed_restart=managed_recovery,
                )
                frame = encode_frame(message)
                payload_len = len(frame) - 4
                if payload_len > MAX_DISCOVERY_PAYLOAD:
                    raise RuntimeError(
                        f"discovery JSON is {payload_len} bytes; controller maximum is {MAX_DISCOVERY_PAYLOAD}"
                    )
                sock.sendto(frame, target)
                log.info(
                    "TX DISCOVERY type=1 seq=%d mac=%s bytes=%d -> %s:%d",
                    seq,
                    normalize_mac(config.MAC),
                    len(frame),
                    target[0],
                    target[1],
                )
                if dump_tx:
                    log.info("TX JSON %s", frame[4:].decode("utf-8"))
                seq = 1 if seq >= 0x7FFFFFFF else seq + 1
                next_send = now + config.DISCOVERY_INTERVAL
                deadline = time.monotonic() + 2.0 if once else None

            try:
                data, addr = sock.recvfrom(65535)
            except socket.timeout:
                if once and deadline is not None and time.monotonic() >= deadline:
                    return
                # A managed discovery may be enough for Controller to rebuild
                # its device image/context without sending PRE_ADOPT. Periodically
                # probe the managed TCP path again, but far less aggressively
                # than the old three-second infinite reconnect loop.
                if managed_recovery and saved_state and time.monotonic() >= next_managed_probe_at:
                    # Only probe occasionally. The UDP rediscovery itself is the
                    # repair mechanism; repeated rapid TCP attempts just recreate
                    # the "adopt info is null" loop seen in server.log.
                    next_managed_probe_at = time.monotonic() + max(10.0, config.DISCOVERY_INTERVAL * 2)
                    try:
                        log.info(
                            "Managed rediscovery probe: retrying TCP/%d after refreshing UDP discovery state",
                            saved_state.manage_port,
                        )
                        result = run_v2_adoption(
                services=services,
                            controller_host=saved_state.controller_host,
                            adopt_port=saved_state.manage_port,
                            controller_id=saved_state.controller_id,
                            dump_json=dump_tx,
                            managed_reconnect=True,
                            known_config_version=saved_state.config_version,
                        )
                        if result.reached_system_verify:
                            _run_saved_managed_session(dump_tx=dump_tx, services=services)
                            return
                    except AuthenticationRejected as exc:
                        log.error(
                            "Managed rediscovery authentication rejected: %s; continuing discovery",
                            exc,
                        )
                    except (EOFError, ConnectionError, OSError, RuntimeError) as exc:
                        log.info(
                            "Controller has not rebuilt managed context yet (%s); continuing UDP rediscovery",
                            exc,
                        )
                continue

            try:
                msg = decode_frame(data)
            except Exception as exc:
                log.warning("RX undecodable UDP datagram from %s: %s; hex=%s", addr, exc, data.hex())
                continue
            log_inbound(msg, addr, dump_json=dump_tx)

            header = msg.get("header") or {}
            body = msg.get("body") or {}
            msg_type = int(header.get("type", -1))
            learned_id = header.get("dest")
            if isinstance(learned_id, str) and learned_id:
                # A 24-character destination is a Site ID in Controller 6.2.
                # Do not overwrite the logical controller ID with a Site ID.
                if len(learned_id) == 24:
                    destination_id = learned_id
                elif not controller_id:
                    controller_id = learned_id

            if msg_type != int(MessageType.PRE_ADOPT_REQUEST):
                continue

            adopt_port = int(body.get("adoptPort") or config.MANAGE_PORT)
            log.warning(
                "PRE_ADOPT_REQUEST received: adoptPort=%d controllerId=%r. Discovery stage is proven.",
                adopt_port,
                controller_id,
            )
            if managed_recovery:
                log.warning(
                    "Controller requested PRE_ADOPT during managed rediscovery; "
                    "recovering automatically with the existing Device Account credentials"
                )
            if no_adopt:
                log.warning("--no-adopt set; not opening the TCP adoption channel")
                continue

            # Keep UDP discovery alive across a rejected Device Account attempt.
            # A new discovery frame can make the controller retry PRE_ADOPT on
            # the same process/NAT mapping after the credentials are corrected.
            try:
                run_v2_adoption(
                    services=services,
                    controller_host=config.CONTROLLER_HOST,
                    adopt_port=adopt_port,
                    controller_id=controller_id,
                    dump_json=dump_tx,
                )
            except AuthenticationRejected as exc:
                log.error(
                    "Device Account authentication rejected: %s Keeping discovery alive for another controller retry.",
                    exc,
                )
                next_send = 0.0
                continue
            except RuntimeError as exc:
                log.error(
                    "Adoption attempt was rejected: %s Keeping discovery alive instead of exiting.",
                    exc,
                )
                next_send = 0.0
                continue

            # run_v2_adoption normally remains here for the lifetime of the
            # manage connection. If it returns after successful sync, state now
            # exists and subsequent connections can bypass manual adoption.
            if services.state_repository.load() is not None:
                break
            next_send = 0.0
    finally:
        sock.close()

    _run_saved_managed_session(dump_tx=dump_tx, services=services)
