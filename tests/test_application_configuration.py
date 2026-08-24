from dataclasses import dataclass

from open_omada_device_agent.application.configuration import ApplyDeviceConfiguration
from open_omada_device_agent.domain import AccessPointConfigUpdate, LedConfig, RadioBand, RadioConfig


@dataclass
class Result:
    applied: bool = True
    changed: bool = False
    error: str = ""


class RecordingPort:
    def __init__(self, result=Result()):
        self.result = result
        self.calls = []

    def reconcile(self, update, capabilities):
        self.calls.append((update, capabilities))
        return self.result


def test_apply_configuration_selects_ports_by_configuration_intent():
    platform = RecordingPort(Result(changed=True))
    commands = RecordingPort()
    use_case = ApplyDeviceConfiguration(
        capability_detector=lambda: "host capabilities",
        platform_ports=(platform,),
        command_ports=(commands,),
    )

    result = use_case.execute(
        AccessPointConfigUpdate(
            sequence_id=1,
            config_version=2,
            config_version_inc=None,
            radios=(RadioConfig(RadioBand.TWO_G),),
        )
    )

    assert result.applied is True
    assert result.changed is True
    assert len(platform.calls) == 1
    assert commands.calls == []


def test_apply_configuration_stops_after_failed_adapter():
    failing = RecordingPort(Result(applied=False, error="platform rejected update"))
    later = RecordingPort()
    use_case = ApplyDeviceConfiguration(
        capability_detector=object,
        platform_ports=(),
        command_ports=(failing, later),
    )

    result = use_case.execute(
        AccessPointConfigUpdate(
            sequence_id=1,
            config_version=2,
            config_version_inc=None,
            led=LedConfig(enabled=True),
        )
    )

    assert result.applied is False
    assert result.error == "platform rejected update"
    assert later.calls == []
