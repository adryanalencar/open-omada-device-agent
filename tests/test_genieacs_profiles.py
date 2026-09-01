from open_omada_device_agent.adapters.outbound.genieacs.capabilities import (
    to_platform_capabilities,
)
from open_omada_device_agent.adapters.outbound.genieacs.models import Tr069DataModel
from open_omada_device_agent.adapters.outbound.genieacs.parameters import normalize_parameters
from open_omada_device_agent.adapters.outbound.genieacs.profiles import (
    GenericTr098Profile,
    GenericTr181Profile,
    UnsupportedTr069Profile,
    select_profile,
)
from open_omada_device_agent.contexts.wireless.domain import RadioBand


def test_selects_tr181_profile_and_derives_capabilities_from_writable_parameters():
    tree = normalize_parameters(
        {
            "_id": "tr181-device",
            "Device": {
                "DeviceInfo": {"Manufacturer": {"_value": "Example"}},
                "WiFi": {
                    "Radio": {
                        "2": {
                            "OperatingFrequencyBand": {"_value": "5GHz"},
                            "Enable": {"_value": True, "_writable": True},
                            "Channel": {"_value": 36, "_writable": False},
                        },
                        "10": {
                            "OperatingFrequencyBand": {"_value": "2.4GHz"},
                            "Enable": {"_value": True, "_writable": False},
                            "AutoChannelEnable": {"_value": True, "_writable": True},
                        },
                    },
                    "SSID": {
                        "1": {
                            "SSID": {"_value": "Media Beach", "_writable": True},
                            "MACAddress": {"_value": "02-11-22-33-44-55"},
                        }
                    },
                    "AccessPoint": {
                        "1": {
                            "Security": {
                                "ModeEnabled": {"_value": "WPA2-Personal", "_writable": True},
                                "KeyPassphrase": {"_value": "", "_writable": True},
                            },
                            "AssociatedDevice": {
                                "1": {
                                    "MACAddress": {"_value": "9E-27-26-62-6D-EC"},
                                    "SignalStrength": {"_value": -55},
                                    "Stats": {
                                        "BytesSent": {"_value": 100},
                                        "BytesReceived": {"_value": 200},
                                    },
                                }
                            },
                        }
                    },
                },
            },
        }
    )

    profile = select_profile(tree)
    capabilities = profile.capabilities(tree)

    assert isinstance(profile, GenericTr181Profile)
    assert profile.radio_refs(tree)[0].path == "Device.WiFi.Radio.2"
    assert profile.radio_refs(tree)[1].path == "Device.WiFi.Radio.10"
    assert capabilities.profile == "tr181_generic"
    assert capabilities.data_model is Tr069DataModel.TR181
    assert capabilities.has_device_info is True
    assert capabilities.has_wifi is True
    assert capabilities.radio_count == 2
    assert capabilities.ssid_count == 1
    assert capabilities.access_point_count == 1
    assert capabilities.client_table_count == 1
    assert capabilities.radio_bands == (RadioBand.FIVE_G, RadioBand.TWO_G)
    assert capabilities.supports_radio_read is True
    assert capabilities.supports_radio_enable is True
    assert capabilities.supports_channel_write is True
    assert capabilities.supports_ssid_read is True
    assert capabilities.supports_ssid_write is True
    assert capabilities.supports_wpa2_psk is True
    assert capabilities.supports_clients is True
    assert capabilities.supports_client_signal is True
    assert capabilities.supports_client_traffic is True
    assert capabilities.supports_portal is False
    assert capabilities.supports_vlan is False


def test_tr181_capabilities_remain_read_only_when_parameters_are_not_writable():
    tree = normalize_parameters(
        {
            "_id": "tr181-readonly",
            "Device": {
                "WiFi": {
                    "Radio": {
                        "1": {
                            "OperatingFrequencyBand": {"_value": "2.4GHz"},
                            "Enable": {"_value": True, "_writable": False},
                            "Channel": {"_value": 6, "_writable": False},
                        }
                    },
                    "SSID": {
                        "1": {
                            "SSID": {"_value": "Read Only", "_writable": False},
                        }
                    },
                }
            },
        }
    )

    capabilities = GenericTr181Profile().capabilities(tree)

    assert capabilities.supports_radio_read is True
    assert capabilities.supports_radio_enable is False
    assert capabilities.supports_channel_write is False
    assert capabilities.supports_ssid_read is True
    assert capabilities.supports_ssid_write is False
    assert capabilities.supports_wpa2_psk is False


def test_selects_tr098_profile_and_does_not_assume_wlan_index_band():
    tree = normalize_parameters(
        {
            "_id": "tr098-device",
            "InternetGatewayDevice": {
                "DeviceInfo": {"Manufacturer": {"_value": "Legacy"}},
                "LANDevice": {
                    "2": {
                        "WLANConfiguration": {
                            "3": {
                                "SSID": {"_value": "Legacy WiFi", "_writable": True},
                                "Enable": {"_value": True, "_writable": True},
                                "Channel": {"_value": 11, "_writable": True},
                                "BeaconType": {"_value": "WPA2", "_writable": True},
                                "AssociatedDevice": {
                                    "5": {
                                        "AssociatedDeviceMACAddress": {
                                            "_value": "AA-BB-CC-DD-EE-FF"
                                        },
                                        "SignalStrength": {"_value": -60},
                                    }
                                },
                            }
                        }
                    }
                },
            },
        }
    )

    profile = select_profile(tree)
    capabilities = profile.capabilities(tree)

    assert isinstance(profile, GenericTr098Profile)
    assert profile.ssid_refs(tree)[0].path == (
        "InternetGatewayDevice.LANDevice.2.WLANConfiguration.3"
    )
    assert capabilities.profile == "tr098_generic"
    assert capabilities.data_model is Tr069DataModel.TR098
    assert capabilities.has_wifi is True
    assert capabilities.radio_count == 1
    assert capabilities.ssid_count == 1
    assert capabilities.client_table_count == 1
    assert capabilities.radio_bands == ()
    assert capabilities.supports_radio_enable is True
    assert capabilities.supports_channel_write is True
    assert capabilities.supports_ssid_write is True
    assert capabilities.supports_wpa2_psk is True
    assert capabilities.supports_clients is True
    assert capabilities.supports_client_signal is True


def test_tr098_profile_reports_band_only_when_parameter_exists():
    tree = normalize_parameters(
        {
            "_id": "tr098-device",
            "InternetGatewayDevice": {
                "LANDevice": {
                    "1": {
                        "WLANConfiguration": {
                            "1": {
                                "SSID": {"_value": "Two G"},
                                "OperatingFrequencyBand": {"_value": "2.4GHz"},
                            },
                            "2": {
                                "SSID": {"_value": "Five G"},
                                "X_HW_Band": {"_value": "5GHz"},
                            },
                        }
                    }
                }
            },
        }
    )

    capabilities = GenericTr098Profile().capabilities(tree)

    assert capabilities.radio_bands == (RadioBand.TWO_G, RadioBand.FIVE_G)


def test_prefers_tr181_when_both_roots_exist_with_modern_wifi_tree():
    tree = normalize_parameters(
        {
            "_id": "dual-device",
            "Device": {
                "WiFi": {
                    "Radio": {"1": {"Enable": {"_value": True}}},
                }
            },
            "InternetGatewayDevice": {
                "LANDevice": {
                    "1": {
                        "WLANConfiguration": {
                            "1": {"SSID": {"_value": "Legacy"}}
                        }
                    }
                }
            },
        }
    )

    assert isinstance(select_profile(tree), GenericTr181Profile)


def test_returns_unsupported_profile_for_unknown_tree():
    tree = normalize_parameters({"_id": "unknown", "Other": {"Root": {"Value": {"_value": 1}}}})

    profile = select_profile(tree)

    assert isinstance(profile, UnsupportedTr069Profile)
    assert profile.capabilities(tree).data_model is Tr069DataModel.UNKNOWN


def test_maps_genieacs_capabilities_to_existing_platform_capabilities_conservatively():
    tree = normalize_parameters(
        {
            "_id": "tr181-device",
            "Device": {
                "WiFi": {
                    "Radio": {
                        "1": {
                            "OperatingFrequencyBand": {"_value": "2.4GHz"},
                            "Enable": {"_value": True, "_writable": True},
                        }
                    },
                    "SSID": {
                        "1": {"SSID": {"_value": "Media Beach", "_writable": True}}
                    },
                }
            },
        }
    )

    platform = to_platform_capabilities(GenericTr181Profile().capabilities(tree))

    assert platform.platform == "genieacs"
    assert platform.radio_bands == (RadioBand.TWO_G,)
    assert platform.max_ssids == 1
    assert platform.supports_wlan_config is True
    assert platform.supports_wpa2_psk is False
    assert platform.supports_portal is False
    assert platform.supports_client_operations is False
