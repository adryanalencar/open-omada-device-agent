# Configuration Reference

Configuration is read from `OMADA_*` environment variables. `python-dotenv`
loads a local `.env` file automatically for development and lab use.

Copy the template:

```bash
cp .env.example .env
```

## Controller transport

| Variable | Default | Description |
| --- | --- | --- |
| `OMADA_CONTROLLER_HOST` | required | Controller hostname or IP |
| `OMADA_DISCOVERY_PORT` | `29810` | UDP discovery port |
| `OMADA_MANAGE_PORT` | `29814` | Default ECSP V2 management port |
| `OMADA_LOCAL_DISCOVERY_PORT` | `0` | Local UDP source port; `0` lets the OS choose |
| `OMADA_DISCOVERY_INTERVAL` | `5` | Discovery interval in seconds |
| `OMADA_TCP_TIMEOUT` | `15` | Management socket timeout |
| `OMADA_INFORM_INTERVAL` | `3` | Managed inform interval |
| `OMADA_RECONNECT_DELAY` | `3` | Delay between direct reconnect attempts |
| `OMADA_MANAGED_RECONNECT_ATTEMPTS` | `3` | Failures before managed rediscovery |

## Controller and site routing

| Variable | Description |
| --- | --- |
| `OMADA_CONTROLLER_ID` | Logical controller identifier used by the ECSP management session |
| `OMADA_SITE_ID` | Site-scoped destination used by discovery when known |
| `OMADA_DEST_OMADAC_ID` | Low-level discovery destination override when no Site ID is used |

For the tested Controller 6.2 family, Controller IDs are typically 32
characters and Site IDs 24 characters.

## Device identity

| Variable | Default |
| --- | --- |
| `OMADA_DEVICE_MAC` | `02:00:00:00:00:01` |
| `OMADA_DEVICE_NAME` | `OpenOmada-AP` |
| `OMADA_DEVICE_MODEL` | `EAP110` |
| `OMADA_DEVICE_MODEL_VERSION` | `4.0` |
| `OMADA_DEVICE_HARDWARE_VERSION` | `4.0` |
| `OMADA_DEVICE_FIRMWARE_VERSION` | `5.0.4` |
| `OMADA_CUSTOMIZE_REGION` | `841` |
| `OMADA_DEVICE_IP` | `0.0.0.0` |

`OMADA_DEVICE_IP=auto` enables a best-effort external public-IP lookup. This is
off by default so the agent does not unexpectedly contact a third-party service.

## Device Account authentication

| Variable | Description |
| --- | --- |
| `OMADA_DEVICE_USERNAME` | Optional explicit Device Account username |
| `OMADA_DEVICE_PASSWORD` | Device Account password; required for the current verification path |
| `OMADA_DEVICE_CIPHER_TYPE` | Current implementation expects `5` |

If the username is omitted, the agent requests it from the controller during
pre-connect.

Never commit `.env`.

## TLS

| Variable | Default | Description |
| --- | --- | --- |
| `OMADA_TLS_VERIFY` | `false` | Verify the controller's TLS certificate |
| `OMADA_TLS_CA_FILE` | empty | Optional custom CA file |

For a trusted deployment:

```dotenv
OMADA_TLS_VERIFY=true
OMADA_TLS_CA_FILE=/etc/open-omada/controller-ca.pem
```

## Uplink telemetry

| Variable | Default | Description |
| --- | --- | --- |
| `OMADA_LAN_RATE` | `100` | Reported wired link rate |
| `OMADA_LAN_DUPLEX` | `1` | Duplex value used by the reference profile |
| `OMADA_LAN_PORT` | `LAN` | Uplink port label |

## AP platform features

| Variable | Default | Description |
| --- | --- | --- |
| `OMADA_PLATFORM` | `auto` | `auto`, `openwrt`, or `generic` capability detection |
| `OMADA_RADIO_BANDS` | `2g` | Comma-separated supported AP bands: `2g,5g,5g2,6g` |
| `OMADA_MAX_SSIDS` | `4` | Maximum SSIDs the platform adapter will accept |
| `OMADA_CAP_WLAN` | auto on OpenWrt with `uci` | Enable WLAN/radio UCI reconciliation |
| `OMADA_CAP_WPA2_PSK` | auto on OpenWrt with `uci` | Accept WPA2-PSK WLANs |
| `OMADA_CAP_WPA3_PSK` | `false` | Accept WPA3-PSK WLANs |
| `OMADA_CAP_SSID_VLAN` | `false` | Accept SSID VLAN mapping |
| `OMADA_CAP_DYNAMIC_VLAN` | `false` | Accept dynamic VLAN requests |
| `OMADA_CAP_MANAGEMENT_VLAN` | `false` | Accept management VLAN requests |
| `OMADA_CAP_PORTAL` | `false` | Reserved; portal WLAN provisioning is still rejected |
| `OMADA_CAP_DHCP_TRACKING` | auto on OpenWrt with `ubus` | Include observed DHCP lease clients |
| `OMADA_CAP_OPTION82` | `false` | Accept DHCP Option 82 WLAN settings |
| `OMADA_CAP_LED` | path-based | Enable sysfs LED brightness writes |

Unsupported controller keys are intentionally rejected with a local
`SET_RESPONSE.errcode=1`.

## DHCP/client tracking

| Variable | Default | Description |
| --- | --- | --- |
| `OMADA_DHCP_LEASE_FILE` | `/tmp/dhcp.leases` | dnsmasq lease file used to report real IP/hostname client data |

If the lease file is absent, client entries are omitted.

## LED control

| Variable | Default | Description |
| --- | --- | --- |
| `OMADA_LED_BRIGHTNESS_PATH` | empty | sysfs brightness file for `led.enable` |
| `OMADA_LED_ON_VALUE` | `1` | Value written when Controller enables the LED |
| `OMADA_LED_OFF_VALUE` | `0` | Value written when Controller disables the LED |

`led.locate` and `wifiControlLed` are parsed but rejected until trigger/button
semantics are implemented.

## State file

The default state file is derived from the device MAC:

```text
.omada-agent-state-020000000001.json
```

Override with `OMADA_STATE_FILE` when needed. The file is Git-ignored by
default.
