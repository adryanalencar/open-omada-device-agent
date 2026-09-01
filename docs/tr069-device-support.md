# TR-069 Device Support Matrix

This table tracks validated GenieACS-backed profile support. Do not add vendor
rows until they are backed by sanitized real parameter trees and tests.

| Vendor | Model | Data model | SSID | PSK | Radio | Clients | VLAN | Portal | Tested firmware | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Generic | Generic TR-181 | `Device.*` | 🟡 detected when writable | 🟡 detected when writable | 🟡 detected from `Device.WiFi.Radio` | 🟡 detected from `AssociatedDevice` | ❌ unavailable | ❌ unavailable | Not tested | Phase 2 fixture-tested profile detection only |
| Generic | Generic TR-098 | `InternetGatewayDevice.*` | 🟡 detected when writable | 🟡 detected when writable | 🟡 detected from `WLANConfiguration` | 🟡 detected from `AssociatedDevice` | ❌ unavailable | ❌ unavailable | Not tested | Phase 2 fixture-tested profile detection only |

Legend:

- ✅ tested
- 🟡 partial
- 🚧 planned
- ❌ unavailable
