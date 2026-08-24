from open_omada_device_agent.domain import PortalClientState
from open_omada_device_agent.portal import PortalSessionManager


def test_portal_session_lifecycle_authenticate_logout_and_block():
    now = 1000
    manager = PortalSessionManager(now=lambda: now)

    session = manager.observe_client("aa-bb-cc-dd-ee-ff", ssid="guest", ipv4="192.0.2.10")
    assert session.state is PortalClientState.UNAUTHENTICATED

    session = manager.start_authentication("aa:bb:cc:dd:ee:ff")
    assert session.state is PortalClientState.AUTHENTICATING

    session = manager.authenticate(
        "aa:bb:cc:dd:ee:ff",
        username="alice",
        token="token-value",
        session_timeout=60,
    )
    assert session.authenticated is True
    assert session.username == "alice"
    assert session.expires_at == 1060

    session = manager.logout("aa:bb:cc:dd:ee:ff")
    assert session.state is PortalClientState.UNAUTHENTICATED
    assert session.username is None
    assert session.token is None

    session = manager.block("aa:bb:cc:dd:ee:ff")
    assert session.state is PortalClientState.BLOCKED


def test_portal_expiration_and_traffic_update():
    current_time = {"value": 1000}
    manager = PortalSessionManager(now=lambda: current_time["value"])
    manager.observe_client("02:00:00:00:00:01")
    manager.authenticate("02:00:00:00:00:01", session_timeout=10)
    manager.update_traffic("02:00:00:00:00:01", rx_bytes=123, tx_bytes=456)

    assert manager.get("02:00:00:00:00:01").rx_bytes == 123

    current_time["value"] = 1010
    expired = manager.expire_due_sessions()

    assert len(expired) == 1
    assert expired[0].state is PortalClientState.EXPIRED
    assert manager.get("02:00:00:00:00:01").authenticated is False
