"""Generic TR-181 profile for GenieACS-backed devices."""
from __future__ import annotations

from collections.abc import Iterable

from .....contexts.wireless.domain import RadioBand
from ..identity import TR181_IDENTITY_PATHS, TR181_MAC_CANDIDATES, extract_identity
from ..models import GenieAcsCapabilities, GenieAcsDeviceIdentity, Tr069DataModel, Tr069ObjectRef
from ..parameters import ParameterTree
from .base import any_writable, band_from_value, instance_refs, path_exists


class GenericTr181Profile:
    name = "tr181_generic"
    data_model = Tr069DataModel.TR181

    def matches(self, tree: ParameterTree) -> bool:
        return tree.root_exists("Device") and (
            tree.has_prefix("Device.WiFi")
            or tree.has_prefix("Device.DeviceInfo")
            or tree.has_prefix("Device.Ethernet")
        )

    def identity(
        self,
        tree: ParameterTree,
        *,
        preferred_mac_paths: Iterable[str] = (),
    ) -> GenieAcsDeviceIdentity:
        return extract_identity(
            tree,
            identity_paths=TR181_IDENTITY_PATHS,
            mac_candidates=TR181_MAC_CANDIDATES,
            preferred_mac_paths=preferred_mac_paths,
        )

    def capabilities(self, tree: ParameterTree) -> GenieAcsCapabilities:
        radios = self.radio_refs(tree)
        ssids = self.ssid_refs(tree)
        aps = self.access_point_refs(tree)
        clients = self.client_table_refs(tree)
        return GenieAcsCapabilities(
            profile=self.name,
            data_model=self.data_model,
            has_device_info=tree.has_prefix("Device.DeviceInfo"),
            has_wifi=tree.has_prefix("Device.WiFi"),
            radio_count=len(radios),
            ssid_count=len(ssids),
            access_point_count=len(aps),
            client_table_count=len(clients),
            radio_bands=self.radio_bands(tree),
            supports_radio_read=bool(radios),
            supports_radio_enable=any_writable(tree, (f"{radio.path}.Enable" for radio in radios)),
            supports_channel_write=any_writable(
                tree,
                (
                    path
                    for radio in radios
                    for path in (f"{radio.path}.Channel", f"{radio.path}.AutoChannelEnable")
                ),
            ),
            supports_ssid_read=path_exists(tree, (f"{ssid.path}.SSID" for ssid in ssids)),
            supports_ssid_write=any_writable(
                tree,
                (
                    path
                    for ssid in ssids
                    for path in (f"{ssid.path}.SSID", f"{ssid.path}.Enable")
                ),
            ),
            supports_wpa2_psk=any_writable(
                tree,
                (
                    path
                    for ap in aps
                    for path in (
                        f"{ap.path}.Security.KeyPassphrase",
                        f"{ap.path}.Security.PreSharedKey.1.KeyPassphrase",
                        f"{ap.path}.Security.ModeEnabled",
                    )
                )
            ),
            supports_clients=bool(clients) or path_exists(
                tree,
                (f"{ap.path}.AssociatedDeviceNumberOfEntries" for ap in aps),
            ),
            supports_client_signal=path_exists(
                tree,
                (f"{client.path}.SignalStrength" for client in clients),
            ),
            supports_client_traffic=path_exists(
                tree,
                (
                    path
                    for client in clients
                    for path in (
                        f"{client.path}.Stats.BytesSent",
                        f"{client.path}.Stats.BytesReceived",
                        f"{client.path}.Stats.PacketsSent",
                        f"{client.path}.Stats.PacketsReceived",
                    )
                )
            ),
            supports_vlan=False,
            supports_portal=False,
            supports_client_control=False,
        )

    def radio_refs(self, tree: ParameterTree) -> tuple[Tr069ObjectRef, ...]:
        return instance_refs(tree, "Device.WiFi.Radio")

    def ssid_refs(self, tree: ParameterTree) -> tuple[Tr069ObjectRef, ...]:
        return instance_refs(tree, "Device.WiFi.SSID")

    def access_point_refs(self, tree: ParameterTree) -> tuple[Tr069ObjectRef, ...]:
        return instance_refs(tree, "Device.WiFi.AccessPoint")

    def client_table_refs(self, tree: ParameterTree) -> tuple[Tr069ObjectRef, ...]:
        refs: list[Tr069ObjectRef] = []
        for ap in self.access_point_refs(tree):
            refs.extend(instance_refs(tree, f"{ap.path}.AssociatedDevice"))
        return tuple(refs)

    def radio_bands(self, tree: ParameterTree) -> tuple[RadioBand, ...]:
        bands: list[RadioBand] = []
        for radio in self.radio_refs(tree):
            for path in (
                f"{radio.path}.OperatingFrequencyBand",
                f"{radio.path}.SupportedFrequencyBands",
            ):
                band = band_from_value(tree.get_or_missing(path).as_string())
                if band is not None:
                    bands.append(band)
                    break
        return tuple(dict.fromkeys(bands))
