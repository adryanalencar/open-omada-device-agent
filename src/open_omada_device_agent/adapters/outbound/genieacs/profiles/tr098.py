"""Generic TR-098 profile for GenieACS-backed devices."""
from __future__ import annotations

from collections.abc import Iterable

from .....contexts.wireless.domain import RadioBand
from ..identity import TR098_IDENTITY_PATHS, TR098_MAC_CANDIDATES, extract_identity
from ..models import GenieAcsCapabilities, GenieAcsDeviceIdentity, Tr069DataModel, Tr069ObjectRef
from ..parameters import ParameterTree
from .base import any_writable, band_from_value, instance_refs, path_exists


class GenericTr098Profile:
    name = "tr098_generic"
    data_model = Tr069DataModel.TR098

    def matches(self, tree: ParameterTree) -> bool:
        return tree.root_exists("InternetGatewayDevice") and (
            tree.has_prefix("InternetGatewayDevice.DeviceInfo")
            or tree.has_prefix("InternetGatewayDevice.LANDevice")
        )

    def identity(
        self,
        tree: ParameterTree,
        *,
        preferred_mac_paths: Iterable[str] = (),
    ) -> GenieAcsDeviceIdentity:
        return extract_identity(
            tree,
            identity_paths=TR098_IDENTITY_PATHS,
            mac_candidates=TR098_MAC_CANDIDATES,
            preferred_mac_paths=preferred_mac_paths,
        )

    def capabilities(self, tree: ParameterTree) -> GenieAcsCapabilities:
        wlans = self.ssid_refs(tree)
        clients = self.client_table_refs(tree)
        return GenieAcsCapabilities(
            profile=self.name,
            data_model=self.data_model,
            has_device_info=tree.has_prefix("InternetGatewayDevice.DeviceInfo"),
            has_wifi=bool(wlans),
            radio_count=len(wlans),
            ssid_count=len(wlans),
            access_point_count=len(wlans),
            client_table_count=len(clients),
            radio_bands=self.radio_bands(tree),
            supports_radio_read=bool(wlans),
            supports_radio_enable=any_writable(
                tree,
                (
                    path
                    for wlan in wlans
                    for path in (f"{wlan.path}.Enable", f"{wlan.path}.RadioEnabled")
                ),
            ),
            supports_channel_write=any_writable(
                tree,
                (f"{wlan.path}.Channel" for wlan in wlans),
            ),
            supports_ssid_read=path_exists(tree, (f"{wlan.path}.SSID" for wlan in wlans)),
            supports_ssid_write=any_writable(tree, (f"{wlan.path}.SSID" for wlan in wlans)),
            supports_wpa2_psk=any_writable(
                tree,
                (
                    path
                    for wlan in wlans
                    for path in (
                        f"{wlan.path}.PreSharedKey.1.KeyPassphrase",
                        f"{wlan.path}.KeyPassphrase",
                        f"{wlan.path}.BeaconType",
                        f"{wlan.path}.BasicEncryptionModes",
                        f"{wlan.path}.BasicAuthenticationMode",
                    )
                )
            ),
            supports_clients=bool(clients),
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
        return self.ssid_refs(tree)

    def ssid_refs(self, tree: ParameterTree) -> tuple[Tr069ObjectRef, ...]:
        refs: list[Tr069ObjectRef] = []
        for lan in instance_refs(tree, "InternetGatewayDevice.LANDevice"):
            refs.extend(instance_refs(tree, f"{lan.path}.WLANConfiguration"))
        return tuple(refs)

    def access_point_refs(self, tree: ParameterTree) -> tuple[Tr069ObjectRef, ...]:
        return self.ssid_refs(tree)

    def client_table_refs(self, tree: ParameterTree) -> tuple[Tr069ObjectRef, ...]:
        refs: list[Tr069ObjectRef] = []
        for wlan in self.ssid_refs(tree):
            refs.extend(instance_refs(tree, f"{wlan.path}.AssociatedDevice"))
        return tuple(refs)

    def radio_bands(self, tree: ParameterTree) -> tuple[RadioBand, ...]:
        bands: list[RadioBand] = []
        for wlan in self.ssid_refs(tree):
            for path in (
                f"{wlan.path}.OperatingFrequencyBand",
                f"{wlan.path}.X_TP_Band",
                f"{wlan.path}.X_HW_Band",
                f"{wlan.path}.X_ZTE-COM_RFBand",
            ):
                band = band_from_value(tree.get_or_missing(path).as_string())
                if band is not None:
                    bands.append(band)
                    break
        return tuple(dict.fromkeys(bands))
