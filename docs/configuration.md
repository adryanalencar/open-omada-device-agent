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
| `OMADA_MAX_SSIDS` | `4` | Manual upper bound for SSIDs the platform adapter will accept. On OpenWrt, `iw list` can reduce this automatically when the radio does not support multiple AP interfaces. |
| `OMADA_CAP_WLAN` | auto on OpenWrt with `uci` | Enable WLAN/radio UCI reconciliation |
| `OMADA_CAP_WPA2_PSK` | auto on OpenWrt with `uci` | Accept WPA2-PSK WLANs |
| `OMADA_CAP_WPA3_PSK` | `false` | Accept WPA3-PSK WLANs |
| `OMADA_CAP_SSID_VLAN` | `false` | Accept SSID VLAN mapping |
| `OMADA_CAP_DYNAMIC_VLAN` | `false` | Accept dynamic VLAN requests |
| `OMADA_CAP_MANAGEMENT_VLAN` | `false` | Accept management VLAN requests |
| `OMADA_CAP_PORTAL` | auto with OpenWrt + openNDS | Enable portal WLAN acceptance; explicit `false` disables portal acceptance |
| `OMADA_CAP_DHCP_TRACKING` | auto on OpenWrt with `ubus` | Include observed DHCP lease clients |
| `OMADA_CAP_OPTION82` | `false` | Accept DHCP Option 82 WLAN settings |
| `OMADA_CAP_LED` | path-based | Enable sysfs LED brightness/trigger writes |
| `OMADA_CAP_CLIENT_OPERATIONS` | auto on OpenWrt with `ubus` | Enable supported client control commands |
| `OMADA_CAP_CLIENT_RATE_LIMITS` | `false` | Enable nftables client rate-limit enforcement |

## OpenWrt startup bootstrap

The agent runs an idempotent OpenWrt bootstrap before ECSP discovery when
`OMADA_OPENWRT_BOOTSTRAP=true` and the detected platform is OpenWrt. This is
where lab-only manual setup belongs.

| Variable | Default | Description |
| --- | --- | --- |
| `OMADA_OPENWRT_BOOTSTRAP` | `true` | Enable startup self-healing for OpenWrt prerequisites |
| `OMADA_OPENWRT_BOOTSTRAP_LAN` | `true` | Ensure the LAN bridge can exist even with only Wi-Fi ports |
| `OMADA_OPENWRT_LAN_INTERFACE` | `lan` | UCI network interface used by Omada WLANs |
| `OMADA_OPENWRT_LAN_BRIDGE` | `br-lan` | UCI bridge device used by OpenWrt AP interfaces and openNDS |
| `OMADA_OPENWRT_LAN_IPADDR` | `192.168.1.1/24` | LAN address used only when the bootstrap must create a missing LAN interface |
| `OMADA_OPENWRT_BOOTSTRAP_OPENNDS` | `true` | Enable and start openNDS when installed |
| `OMADA_OPENNDS_GATEWAY_PORT` | `2050` | openNDS local gateway port |
| `OMADA_OPENNDS_GATEWAY_NAME` | device name | openNDS gateway name; empty uses `OMADA_DEVICE_NAME` |
| `OMADA_OPENWRT_ENABLE_WAN_MANAGEMENT` | `false` | Lab-only opt-in to open SSH, LuCI HTTP, and LuCI HTTPS from the WAN zone |
| `OMADA_OPENWRT_WAN_ZONE` | `wan` | Firewall zone used by the WAN management opt-in rules |

The LAN bootstrap sets `bridge_empty=1` on the bridge device. This is required
on Wi-Fi-only OpenWrt devices where `br-lan` otherwise does not exist until a
radio interface is already attached, which prevents hostapd/openNDS from
starting cleanly.

## OpenWrt targets

| Variable | Default | Description |
| --- | --- | --- |
| `OMADA_MANAGEMENT_VLAN_INTERFACE` | empty | UCI network interface to update for management VLAN |
| `OMADA_MANAGEMENT_VLAN_DEVICE` | empty | Base OpenWrt device, for example `br-lan` |
| `OMADA_HOSTAPD_UBUS_IFACE` | empty | hostapd ubus object suffix for reconnect/deauth, for example `wlan0` |
| `OMADA_CLIENT_BLOCK_INTERFACE` | empty | Bridge/interface used by nftables client block rules |
| `OMADA_CLIENT_RATE_LIMIT_INTERFACE` | empty | Bridge/interface used by nftables per-client rate-limit rules |
| `OMADA_PORTAL_INTERFACE` | empty | Fallback nftables-only portal interface; unused when openNDS is installed |
| `OMADA_PORTAL_REDIRECT_PORT` | `8080` | Fallback nftables-only local HTTP redirect port; unused when openNDS is installed |

Unsupported controller keys are intentionally rejected with a local
`SET_RESPONSE.errcode=1`.

## Captive portal on OpenWrt

Use `openNDS` as the OpenWrt captive portal engine. The built-in nftables
adapter remains only as a fallback for lab setups without openNDS.

For OpenWrt 25 snapshots:

```bash
apk update
apk add opennds dnsmasq-full conntrack
```

For older OpenWrt package feeds:

```bash
opkg update
opkg install opennds dnsmasq-full conntrack
```

Minimal UCI example:

```bash
uci set opennds.@opennds[0].enabled='1'
uci set opennds.@opennds[0].gatewayinterface='br-lan'
uci set opennds.@opennds[0].gatewayport='2050'
uci commit opennds
/etc/init.d/opennds restart
```

With openNDS installed, the agent:

- reports portal client state from `ndsctl json`;
- applies `portalFreePolicyConfig` URL rules as openNDS walled-garden FQDNs;
- applies `portalFreePolicyConfig` IP rules as openNDS preauthenticated user
  rules;
- writes `/usr/lib/opennds/theme_openomada_redirect.sh` and sets
  `login_option_enabled=3` when Omada provides a portal URL through
  `portalConfigList` or a `/portal/...` free-policy URL;
- sets `allow_preemptive_authentication=0` so clients use the classic HTTP
  redirect path instead of stopping at the openNDS RFC8910 status page;
- applies `clientConfig.unauth=false` with `ndsctl auth`;
- applies `clientConfig.unauth=true` with `ndsctl deauth`;
- clears conntrack entries for the client IP after deauth when `conntrack` is
  installed;
- does not install its own `inet openomada_portal` table.

The generated ThemeSpec redirects only to the configured portal URL. It does not
append client MAC, client IP, or original URL parameters until the Omada
`/portal/entry` parameter contract is mapped safely.

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
| `OMADA_LED_TRIGGER_PATH` | empty | sysfs trigger file for `led.locate` |
| `OMADA_LED_LOCATE_TRIGGER` | `timer` | Trigger value while locate is active |
| `OMADA_LED_DEFAULT_TRIGGER` | `none` | Trigger value restored when locate stops |

`wifiControlLed` is parsed but rejected because it represents hardware button
semantics, not the LED brightness/locate state itself.

## State file

The default state file is derived from the device MAC:

```text
.omada-agent-state-020000000001.json
```

Override with `OMADA_STATE_FILE` when needed. The file is Git-ignored by
default.
