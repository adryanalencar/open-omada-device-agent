"""Reference access-point profile backed by generic Linux observations."""
from collections.abc import Callable
from typing import Any

from ....application.contracts import PlatformCapabilities
from ....application.settings import AgentSettings
from ....capabilities import ap_components_v2
from ....contexts.device.domain import DeviceIdentity
from ....contexts.wireless.domain import RadioBand
from ....shared.domain import MacAddress
from ....system_tools import get_cpu_utilization, get_memory_utilization, get_system_uptime


RADIO_ID_BY_BAND: dict[RadioBand, int] = {
    RadioBand.TWO_G: 0,
    RadioBand.FIVE_G: 1,
    RadioBand.FIVE_G2: 2,
    RadioBand.SIX_G: 3,
}

BAND_LABEL_BY_BAND: dict[RadioBand, str] = {
    RadioBand.TWO_G: "2.4G",
    RadioBand.FIVE_G: "5G",
    RadioBand.FIVE_G2: "5G2",
    RadioBand.SIX_G: "6G",
}

# Omada stores channel width support as regulatory-domain bit flags. These
# values are the same constants used by Controller 6.2.14.11's channel code.
WIDTH_FLAG_2G_HT40 = 0x20000 | 0x40000
WIDTH_FLAG_5G_HT40_VHT80 = 0x20000 | 0x40000 | 0x800100
WIDTH_FLAG_6G_20_40_80_160 = 0x100 | 0x20000 | 0x40000 | 0x800000 | 0x1000000

CHANNELS_BY_BAND: dict[RadioBand, tuple[tuple[int, int, int, int], ...]] = {
    RadioBand.TWO_G: tuple(
        (channel, 2407 + channel * 5, 20, WIDTH_FLAG_2G_HT40)
        for channel in range(1, 14)
    ),
    RadioBand.FIVE_G: (
        (36, 5180, 23, WIDTH_FLAG_5G_HT40_VHT80),
        (40, 5200, 23, WIDTH_FLAG_5G_HT40_VHT80),
        (44, 5220, 23, WIDTH_FLAG_5G_HT40_VHT80),
        (48, 5240, 23, WIDTH_FLAG_5G_HT40_VHT80),
        (149, 5745, 23, WIDTH_FLAG_5G_HT40_VHT80),
        (153, 5765, 23, WIDTH_FLAG_5G_HT40_VHT80),
        (157, 5785, 23, WIDTH_FLAG_5G_HT40_VHT80),
        (161, 5805, 23, WIDTH_FLAG_5G_HT40_VHT80),
        (165, 5825, 23, WIDTH_FLAG_5G_HT40_VHT80),
    ),
    RadioBand.FIVE_G2: (
        (149, 5745, 23, WIDTH_FLAG_5G_HT40_VHT80),
        (153, 5765, 23, WIDTH_FLAG_5G_HT40_VHT80),
        (157, 5785, 23, WIDTH_FLAG_5G_HT40_VHT80),
        (161, 5805, 23, WIDTH_FLAG_5G_HT40_VHT80),
        (165, 5825, 23, WIDTH_FLAG_5G_HT40_VHT80),
    ),
    RadioBand.SIX_G: (
        (5, 5975, 23, WIDTH_FLAG_6G_20_40_80_160),
        (21, 6055, 23, WIDTH_FLAG_6G_20_40_80_160),
        (37, 6135, 23, WIDTH_FLAG_6G_20_40_80_160),
        (53, 6215, 23, WIDTH_FLAG_6G_20_40_80_160),
        (69, 6295, 23, WIDTH_FLAG_6G_20_40_80_160),
    ),
}


class GenericOpenWrtAccessPointProfile:
    def __init__(
        self,
        settings: AgentSettings,
        *,
        ip_address: Callable[[], str],
        capabilities: PlatformCapabilities,
    ) -> None:
        self._settings = settings
        self._ip_address = ip_address
        self._capabilities = capabilities

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
        return ap_components_v2(self._capabilities)

    def channel_info(self) -> tuple[dict[str, Any], ...]:
        if not self._capabilities.supports_wlan_config:
            return ()
        return tuple(
            {
                "radioId": RADIO_ID_BY_BAND[band],
                "band": BAND_LABEL_BY_BAND[band],
                "channelList": [
                    _channel_detail(channel, freq, max_power, width_flag)
                    for channel, freq, max_power, width_flag in CHANNELS_BY_BAND[band]
                ],
            }
            for band in self._capabilities.radio_bands
            if band in CHANNELS_BY_BAND
        )

    def radio_cap(self) -> tuple[dict[str, Any], ...]:
        if not self._capabilities.supports_wlan_config:
            return ()
        max_ssids = max(1, self._capabilities.max_ssids)
        return tuple(
            _radio_cap_item(RADIO_ID_BY_BAND[band], max_ssids=max_ssids)
            for band in self._capabilities.radio_bands
            if band in RADIO_ID_BY_BAND
        )


def _radio_cap_item(radio_id: int, *, max_ssids: int) -> dict[str, Any]:
    return {
        "radioId": radio_id,
        "minPow": 1,
        "maxPow": 20,
        "maxPowOd": 20,
        "limitMaxPow": 20,
        "mimo": 1,
        "ofdma": 0,
        "ofdmaEnable": 0,
        "mcsLevel": 7,
        "supportSsidNum": max_ssids,
        "supportAntennaDirection": [],
        "supportMaxClient": 64,
        "supportMlo": False,
        "supportMaxAssocClient": 64,
        "supportAnteGainSetting": 0,
        "supportCSA": 0,
        "supportCSAWidth": 0,
        "supportMgtSsid": 0,
    }


def _channel_detail(
    channel: int,
    freq: int,
    max_power: int,
    width_flag: int,
) -> dict[str, int]:
    return {
        "fr": freq,
        "vl": channel,
        "mPow": max_power,
        "cFlag": width_flag,
        "dFlag": 0,
        "lm": 1,
        "mPowOd": 0,
        "cFlagOd": 0,
    }
