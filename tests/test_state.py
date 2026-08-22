import json

from open_omada_device_agent import config
from open_omada_device_agent.ecsp import normalize_mac
from open_omada_device_agent.session_state import clear_state, load_state, save_state


def test_managed_state_round_trip_does_not_persist_password(tmp_path):
    path = tmp_path / "state.json"
    saved = save_state(
        controller_id="0123456789abcdef0123456789abcdef",
        manage_port=29814,
        site_id="0123456789abcdef01234567",
        username="lab-user",
        config_version=7,
        sequence_id=9,
        path=path,
    )

    assert saved.mac == normalize_mac(config.MAC)
    loaded = load_state(path)
    assert loaded == saved
    raw = json.loads(path.read_text())
    assert raw["manage_port"] == 29814
    assert "password" not in raw
    assert "device_password" not in raw


def test_clear_managed_state(tmp_path):
    path = tmp_path / "state.json"
    save_state(
        controller_id="0123456789abcdef0123456789abcdef",
        manage_port=29814,
        path=path,
    )
    assert clear_state(path) is True
    assert load_state(path) is None
    assert clear_state(path) is False
