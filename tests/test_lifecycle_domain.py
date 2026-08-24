import pytest

from open_omada_device_agent.contexts.lifecycle.domain import ControllerSession, LifecycleState


def test_controller_session_exposes_valid_managed_lifecycle():
    session = ControllerSession().transition(LifecycleState.DISCOVERING)
    session = session.transition(LifecycleState.ADOPTING)
    session = session.transition(LifecycleState.VERIFYING)
    session = session.transition(LifecycleState.NEGOTIATING)
    session = session.transition(LifecycleState.MANAGED)

    assert session.state is LifecycleState.MANAGED


def test_controller_session_rejects_skipping_authentication():
    with pytest.raises(ValueError, match="invalid lifecycle transition"):
        ControllerSession().transition(LifecycleState.MANAGED)
