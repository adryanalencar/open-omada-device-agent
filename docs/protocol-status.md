# Protocol Support Matrix

This table tracks **implementation status**, not merely known numeric message
identifiers.

| Family | Status | Notes |
| --- | --- | --- |
| Discovery | ✅ | Site-scoped UDP discovery implemented |
| Pre-adopt | ✅ | `adoptPort` honored |
| Pre-connect | ✅ | First adoption and `rebuild=1` managed reconnect |
| Device verification | ✅ | Legacy V2 `cipherType=5` branch |
| System verification | ✅ | Mutual auth checked before success |
| Device negotiation | ✅ | Conservative AP component map |
| System negotiation | ✅ | Config/version metadata consumed |
| Initial sync result | ✅ | ACK validated |
| Inform | 🟡 | Device, wired LAN, DHCP lease clients, hostapd station metrics, and OpenWrt `wSettings_*` / `ssidStats_*` when `ubus` is available |
| SET | 🟡 | Envelope/version ACKs plus parsed AP domains; unsupported keys return local error instead of fake success |
| WLAN/radio config | 🟡 | OpenWrt UCI adapter for basic radios and PSK SSIDs |
| SSID VLAN config | 🟡 | Opt-in UCI network interface mapping; dynamic VLAN/Option82 remain rejected unless implemented |
| Management VLAN config | 🟡 | Opt-in UCI device remapping via explicit local target variables |
| Client operations | 🟡 | Reconnect/deauth through hostapd `ubus`; block/unblock and rate-limits through nftables bridge policy |
| LED config | 🟡 | Optional sysfs brightness adapter for `led.enable`; optional trigger adapter for `led.locate`; `wifiControlLed` remains rejected |
| FORGET | ✅ | `FORGET_REQUEST` and no-reset variant are ACKed and clear local reconnect state |
| GET | 🟡 | Handler replies with correlated `GET_RESPONSE` and unsupported-key metadata |
| NOTIFY | 🟡 | Handler replies to v1/v2 notify requests unless `nre=1`; payload-specific handlers are not implemented |
| REPORT | 🚧 | Identifier known; report schemas not implemented |
| Upgrade | 🚧 | Not implemented |
| File transfer | 🚧 | Not implemented |
| Remote terminal | 🚧 | Not implemented |
| Radio telemetry | 🟡 | Basic OpenWrt wireless settings from `ubus`; radio traffic counters not emitted until complete counters are available |
| SSID telemetry | 🟡 | OpenWrt SSID/client counts and optional interface counters |
| Client telemetry | 🟡 | DHCP lease backed IP/hostname merged with hostapd station RSSI/rate/traffic where available |
| Captive portal | 🟡 | openNDS enforcement, free-policy walled garden, TP-Link EAP External Portal query redirects, `clientConfig.unauth`, and client-state reporting are available on OpenWrt; hosted portal UI and Controller `/hotspot/extPortal/auth` submission are external to the agent |
| Mesh | 🚧 | Not implemented |
| Switch profile | 🚧 | Not implemented |
| Gateway profile | 🚧 | Not implemented |
| OLT profile | 🚧 | Not implemented |

## Capability policy

A protocol component should not be added to the advertised component map merely
because its name/version is known. It should be advertised only after the agent
can safely process the controller behavior that enabling the component causes.
