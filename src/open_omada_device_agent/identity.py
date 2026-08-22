from __future__ import annotations

from . import config
from .ecsp import normalize_mac
from .network_tools import get_public_ip
from .system_tools import get_cpu_utilization, get_memory_utilization, get_system_uptime


def device_info() -> dict:
    mac = normalize_mac(config.MAC)
    ip_address = get_public_ip()
    up_time = get_system_uptime()
    cpu_utilization = get_cpu_utilization()
    mem_utilization = get_memory_utilization()

    return {
        "ip": ip_address,
        "isFactory": True,
        "name": config.DEVICE_NAME,
        "model": config.MODEL,
        "modelVersion": config.MODEL_VERSION,
        "firmwareVersion": config.FIRMWARE_VERSION,
        "hardwareVersion": config.HARDWARE_VERSION,
        "upTime": up_time,
        "cpuUti": cpu_utilization,
        "memUti": mem_utilization,
        "wirelessLinked": False,
        "p2p": False,
        "supportBridge": 0,
        "mainMac": mac,
    }


def device_misc() -> dict:
    return {
        "modelType": "NORMAL",
        "support_11ac": False,
        "support_lag": False,
        "supportMesh": 0,
        "customizeRegion": config.CUSTOMIZE_REGION,
        "support_channelLimit": False,
        "channelLimit_mode": 0,
        "supportDfs": 0,
        "lanPortsNum": 1,
        "lanVlanPorts": [],
        "lanPoePorts": [],
        "supportRoaming": 0,
    }


def controller_setting(controller_id: str, destination_id: str = "") -> dict:
    return {
        "controllerId": controller_id,
        "destOmadacId": destination_id or controller_id,
    }
