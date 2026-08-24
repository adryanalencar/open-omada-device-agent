from dataclasses import replace

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
