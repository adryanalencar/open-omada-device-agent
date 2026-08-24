"""Reference access-point profile backed by generic Linux observations."""
from collections.abc import Callable
from typing import Any

from ....application.settings import AgentSettings
from ....contexts.device.domain import DeviceIdentity
from ....shared.domain import MacAddress
from ....capabilities import ap_components_v2
from ....system_tools import get_cpu_utilization, get_memory_utilization, get_system_uptime


class GenericOpenWrtAccessPointProfile:
    def __init__(self, settings: AgentSettings, *, ip_address: Callable[[], str]) -> None:
        self._settings = settings
        self._ip_address = ip_address

    def identity(self) -> DeviceIdentity:
        return DeviceIdentity(
            mac=MacAddress(self._settings.mac),
            name=self._settings.device_name,
            model=self._settings.model,
            model_version=self._settings.model_version,
            hardware_version=self._settings.hardware_version,
            firmware_version=self._settings.firmware_version,
        )

    def device_info(self) -> dict[str, Any]:
        identity = self.identity()
        return {
            "ip": self._ip_address(),
            "isFactory": True,
            "name": identity.name,
            "model": identity.model,
            "modelVersion": identity.model_version,
            "firmwareVersion": identity.firmware_version,
            "hardwareVersion": identity.hardware_version,
            "upTime": get_system_uptime(),
            "cpuUti": get_cpu_utilization(),
            "memUti": get_memory_utilization(),
            "wirelessLinked": False,
            "p2p": False,
            "supportBridge": 0,
            "mainMac": identity.mac.value,
        }

    def device_misc(self) -> dict[str, Any]:
        return {
            "modelType": "NORMAL",
            "support_11ac": False,
            "support_lag": False,
            "supportMesh": 0,
            "customizeRegion": self._settings.customize_region,
            "support_channelLimit": False,
            "channelLimit_mode": 0,
            "supportDfs": 0,
            "lanPortsNum": 1,
            "lanVlanPorts": [],
            "lanPoePorts": [],
            "supportRoaming": 0,
        }

    def components_v2(self) -> dict[str, str]:
        return ap_components_v2()
