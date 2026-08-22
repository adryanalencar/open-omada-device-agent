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
| Inform | ✅ | Minimal device + wired LAN telemetry |
| SET | 🟡 | Envelope/version ACKs; configuration semantics are not broadly applied |
| GET | 🚧 | Message identifiers known; handlers not implemented |
| NOTIFY | 🚧 | Identifiers known; handlers not implemented |
| REPORT | 🚧 | Identifier known; report schemas not implemented |
| Upgrade | 🚧 | Not implemented |
| File transfer | 🚧 | Not implemented |
| Remote terminal | 🚧 | Not implemented |
| Radio telemetry | 🚧 | Reference profile does not yet report realistic radio state |
| SSID telemetry | 🚧 | Not implemented |
| Client telemetry | 🚧 | Not implemented |
| Mesh | 🚧 | Not implemented |
| Switch profile | 🚧 | Not implemented |
| Gateway profile | 🚧 | Not implemented |
| OLT profile | 🚧 | Not implemented |

## Capability policy

A protocol component should not be added to the advertised component map merely
because its name/version is known. It should be advertised only after the agent
can safely process the controller behavior that enabling the component causes.
