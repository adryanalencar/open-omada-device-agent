from dataclasses import replace

import pytest

from open_omada_device_agent.bootstrap import AgentSettings, build_runtime
from open_omada_device_agent.contexts.lifecycle.domain import ManagedState


def test_runtime_uses_injected_settings_for_profile_and_repository(tmp_path):
    settings = replace(
        AgentSettings.from_environment(),
        controller_host="controller.example.test",
        mac="02:00:00:00:12:34",
        device_name="injected-ap",
        state_file=tmp_path / "managed.json",
    )

    runtime = build_runtime(settings)
    identity = runtime.device_profile.identity()
    state = ManagedState(
        version=1,
        mac=identity.mac.value,
        controller_host=settings.controller_host,
        controller_id="controller-id",
        manage_port=settings.manage_port,
    )
    runtime.state_repository.save(state)

    assert identity.name == "injected-ap"
    assert runtime.settings is settings
    assert runtime.state_repository.load() == state


def test_repository_rejects_state_for_a_different_runtime_identity(tmp_path):
    settings = replace(
        AgentSettings.from_environment(),
        controller_host="controller.example.test",
        state_file=tmp_path / "managed.json",
    )
    runtime = build_runtime(settings)
    foreign = ManagedState(
        version=1,
        mac="02:00:00:00:ff:ff",
        controller_host=settings.controller_host,
        controller_id="controller-id",
        manage_port=settings.manage_port,
    )

    try:
        runtime.state_repository.save(foreign)
    except ValueError as exc:
        assert "identity" in str(exc)
    else:
        raise AssertionError("repository accepted state for another device")


def test_settings_repr_redacts_device_password():
    settings = replace(
        AgentSettings.from_environment(),
        device_password="do-not-log-this-secret",
    )

    assert "do-not-log-this-secret" not in repr(settings)


def test_capabilities_use_bootstrap_snapshot_not_later_environment(monkeypatch):
    settings = replace(
        AgentSettings.from_environment(),
        capability_environment=(("OMADA_PLATFORM", "generic"),),
    )
    monkeypatch.setenv("OMADA_PLATFORM", "openwrt")

    runtime = build_runtime(settings)

    assert runtime.capabilities.platform == "generic"


def test_settings_reject_invalid_opennds_gateway_port():
    settings = replace(
        AgentSettings.from_environment(),
        controller_host="controller.example.test",
        opennds_gateway_port=70000,
    )

    with pytest.raises(RuntimeError, match="OMADA_OPENNDS_GATEWAY_PORT"):
        settings.validate()


def test_settings_reject_missing_openwrt_lan_target():
    settings = replace(
        AgentSettings.from_environment(),
        controller_host="controller.example.test",
        openwrt_lan_bridge="",
    )

    with pytest.raises(RuntimeError, match="OMADA_OPENWRT_LAN_INTERFACE"):
        settings.validate()
