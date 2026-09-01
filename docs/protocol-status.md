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
| Inform | 🟡 | Device, wired LAN, active hostapd clients enriched with DHCP/openNDS metadata, portal auth clients, hostapd station metrics, OpenWrt `wSettings_*`, `ssidStats_*`, and aggregate `radioTraffic_*` when `ubus` is available |
| SET | 🟡 | Envelope/version ACKs plus parsed AP domains; unsupported keys return local error instead of fake success; common controller defaults such as `ssh`, `snmp`, `lldp`, `ipGroup`, `ipv6Group`, `lanSetting`, `logSetting`, and scheduler/mac-filter globals are accepted as passive when they do not require OpenWrt changes |
| WLAN/radio config | 🟡 | OpenWrt UCI adapter for basic radios and PSK SSIDs |
| SSID VLAN config | 🟡 | Opt-in UCI network interface mapping; dynamic VLAN/Option82 remain rejected unless implemented |
| Management VLAN config | 🟡 | Opt-in UCI device remapping via explicit local target variables |
| Client operations | 🟡 | Reconnect/deauth through hostapd `ubus`; block/unblock and rate-limits through nftables bridge policy |
| LED config | 🟡 | Optional sysfs brightness adapter for `led.enable`; optional trigger adapter for `led.locate`; `wifiControlLed` remains rejected |
| FORGET | ✅ | `FORGET_REQUEST` and no-reset variant are ACKed and clear local reconnect state |
| GET | 🟡 | Handler replies with correlated `GET_RESPONSE` and unsupported-key metadata |
| NOTIFY | 🟡 | Handler replies to v1/v2 notify requests unless `nre=1`; payload-specific handlers are not implemented |
| REPORT | 🚧 | ECSP identifier and `Report.reportData` envelope are known. AP client report protobuf DTOs were identified (`MonitorMessageDTO`, `ComponentDTO`, `ApClientReportDTO`, `WirelessClientDTO`), but the exact `reportData` string serializer used by device-side REPORT is not implemented yet. |
| Upgrade | 🚧 | Not implemented |
| File transfer | 🚧 | Not implemented |
| Remote terminal | 🚧 | Not implemented |
| Radio telemetry | 🟡 | Basic OpenWrt wireless settings from `ubus`; aggregate `radioTraffic_*` from hostapd bytes/packet counters where available |
| SSID telemetry | 🟡 | OpenWrt SSID/client counts, BSSID in Omada MAC format, optional interface counters, and hostapd traffic counters |
| Client telemetry | 🟡 | Active hostapd station RSSI/SNR/rate/traffic enriched with DHCP IP/hostname and openNDS portal state; stale DHCP/openNDS-only clients are filtered out |
| Captive portal | 🟡 | openNDS enforcement, free-policy walled garden, TP-Link EAP External Portal query redirects, `clientConfig.unauth`, and client-state reporting are available on OpenWrt; hosted portal UI and Controller `/hotspot/extPortal/auth` submission are external to the agent |
| Mesh | 🚧 | Not implemented |
| Switch profile | 🚧 | Not implemented |
| Gateway profile | 🚧 | Not implemented |
| OLT profile | 🚧 | Not implemented |

## Remote-device backends

GenieACS/TR-069 support is in Phase 1 foundation status. The repository now has
configuration fields, a bounded GenieACS NBI HTTP client, task status modeling
that distinguishes immediate execution from queued tasks, and a normalized
parameter-tree abstraction for GenieACS device documents. It is not yet wired
into the ECSP runtime, does not yet advertise GenieACS-derived capabilities, and
does not yet apply Omada SET requests through TR-069.

## Capability policy

A protocol component should not be added to the advertised component map merely
because its name/version is known. It should be advertised only after the agent
can safely process the controller behavior that enabling the component causes.

## MAC serialization policy

The agent keeps MAC addresses internally in normalized lower-case colon form for
comparison and merging. Any MAC emitted toward Omada is converted at the
boundary to `AA-BB-CC-DD-EE-FF`; this includes ECSP headers, `mainMac`, client
stats, SSID BSSID values, RADIUS Calling/Called-Station-Id values, and openNDS
External Portal redirect parameters.
