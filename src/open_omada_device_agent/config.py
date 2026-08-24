"""Environment-backed runtime configuration for Open Omada Device Agent."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)), 0)


def _float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# Controller transport
CONTROLLER_HOST = os.getenv("OMADA_CONTROLLER_HOST", "").strip()
DISCOVERY_PORT = _int("OMADA_DISCOVERY_PORT", 29810)
MANAGE_PORT = _int("OMADA_MANAGE_PORT", 29814)
LOCAL_DISCOVERY_PORT = _int("OMADA_LOCAL_DISCOVERY_PORT", 0)
DISCOVERY_INTERVAL = _float("OMADA_DISCOVERY_INTERVAL", 5.0)
TCP_TIMEOUT = _float("OMADA_TCP_TIMEOUT", 15.0)
INFORM_INTERVAL = _float("OMADA_INFORM_INTERVAL", 3.0)
RECONNECT_DELAY = _float("OMADA_RECONNECT_DELAY", 3.0)
MANAGED_RECONNECT_ATTEMPTS = _int("OMADA_MANAGED_RECONNECT_ATTEMPTS", 3)

# TLS. Omada controllers commonly use a private/self-signed certificate on the
# device management channel, so certificate verification remains opt-in.
TLS_VERIFY = _bool("OMADA_TLS_VERIFY", False)
TLS_CA_FILE = os.getenv("OMADA_TLS_CA_FILE", "").strip()

# Reference device identity. The current implementation has been exercised with
# an EAP110 v4-compatible profile, but every field remains configurable.
MAC = os.getenv("OMADA_DEVICE_MAC", "02:00:00:00:00:01")
DEVICE_NAME = os.getenv("OMADA_DEVICE_NAME", "OpenOmada-AP")
MODEL = os.getenv("OMADA_DEVICE_MODEL", "EAP110")
MODEL_VERSION = os.getenv("OMADA_DEVICE_MODEL_VERSION", "4.0")
HARDWARE_VERSION = os.getenv("OMADA_DEVICE_HARDWARE_VERSION", "4.0")
FIRMWARE_VERSION = os.getenv("OMADA_DEVICE_FIRMWARE_VERSION", "5.0.4")
CUSTOMIZE_REGION = _int("OMADA_CUSTOMIZE_REGION", 841)

# Advertised device IP. Keep 0.0.0.0 by default and let the controller observe
# the transport source address. Set this explicitly when a concrete address is
# required, or use "auto" to perform a best-effort public-IP lookup.
DEVICE_IP = os.getenv("OMADA_DEVICE_IP", "0.0.0.0").strip()
PUBLIC_IP_LOOKUP_URL = os.getenv("OMADA_PUBLIC_IP_LOOKUP_URL", "https://api.ipify.org").strip()
PUBLIC_IP_LOOKUP_TIMEOUT = _float("OMADA_PUBLIC_IP_LOOKUP_TIMEOUT", 2.0)

# Minimal wired-uplink report used by managed informs.
LAN_RATE = _float("OMADA_LAN_RATE", 100.0)
LAN_DUPLEX = _int("OMADA_LAN_DUPLEX", 1)
LAN_PORT = os.getenv("OMADA_LAN_PORT", "LAN")

# Client tracking. In AP mode this is an observation source, not an assertion
# that the AP is the DHCP server. If the file does not exist, informs simply
# omit client entries.
DHCP_LEASE_FILE = os.getenv("OMADA_DHCP_LEASE_FILE", "/tmp/dhcp.leases").strip()

# Optional Linux/OpenWrt sysfs LED control. Leave unset unless the operator has
# mapped a real AP status LED brightness file.
LED_BRIGHTNESS_PATH = os.getenv("OMADA_LED_BRIGHTNESS_PATH", "").strip()
LED_ON_VALUE = os.getenv("OMADA_LED_ON_VALUE", "1")
LED_OFF_VALUE = os.getenv("OMADA_LED_OFF_VALUE", "0")
LED_TRIGGER_PATH = os.getenv("OMADA_LED_TRIGGER_PATH", "").strip()
LED_LOCATE_TRIGGER = os.getenv("OMADA_LED_LOCATE_TRIGGER", "timer")
LED_DEFAULT_TRIGGER = os.getenv("OMADA_LED_DEFAULT_TRIGGER", "none")

# Optional client operations. Reconnect/deauth uses OpenWrt hostapd ubus
# objects, while block/unblock uses an nftables bridge table to drop traffic
# from the client MAC after association.
HOSTAPD_UBUS_IFACE = os.getenv("OMADA_HOSTAPD_UBUS_IFACE", "").strip()
CLIENT_BLOCK_INTERFACE = os.getenv("OMADA_CLIENT_BLOCK_INTERFACE", "").strip()
CLIENT_RATE_LIMIT_INTERFACE = os.getenv("OMADA_CLIENT_RATE_LIMIT_INTERFACE", "").strip()

# Optional captive-portal enforcement. The agent only enforces traffic policy
# and HTTP redirect; a local portal web application must listen on this port.
PORTAL_INTERFACE = os.getenv("OMADA_PORTAL_INTERFACE", "").strip()
PORTAL_REDIRECT_PORT = _int("OMADA_PORTAL_REDIRECT_PORT", 8080)

# Optional management VLAN reconciliation. These must be explicit because the
# wrong OpenWrt network target can move the AP out of reach.
MANAGEMENT_VLAN_INTERFACE = os.getenv("OMADA_MANAGEMENT_VLAN_INTERFACE", "").strip()
MANAGEMENT_VLAN_DEVICE = os.getenv("OMADA_MANAGEMENT_VLAN_DEVICE", "").strip()

# ECSP V2 framing/protocol identity.
ECSP_VERSION = os.getenv("OMADA_ECSP_VERSION", "2.3.0")
ECSP_VER_CAP = _int("OMADA_ECSP_VER_CAP", 2)

# Controller/site routing. A site-scoped discovery destination is a 24-character
# Site ID; the logical controller identity remains separate.
CONTROLLER_ID = os.getenv("OMADA_CONTROLLER_ID", "").strip()
DEST_OMADAC_ID = os.getenv("OMADA_DEST_OMADAC_ID", "").strip()
SITE_ID = os.getenv("OMADA_SITE_ID", "").strip()

# Legacy V2 Device Account authentication. No password default is provided and
# credentials are never persisted to managed state.
DEVICE_USERNAME = os.getenv("OMADA_DEVICE_USERNAME", "").strip()
DEVICE_PASSWORD = os.getenv("OMADA_DEVICE_PASSWORD", "")
DEVICE_CIPHER_TYPE = _int("OMADA_DEVICE_CIPHER_TYPE", 5)

# Keep the historical filename for backward compatibility with existing labs.
_state_mac = MAC.replace(":", "").replace("-", "").lower()
STATE_FILE = os.getenv("OMADA_STATE_FILE", f".omada-agent-state-{_state_mac}.json")


def validate_runtime_config() -> None:
    """Validate fields required before network I/O begins."""
    if not CONTROLLER_HOST:
        raise RuntimeError(
            "OMADA_CONTROLLER_HOST is required. Copy .env.example to .env and configure your controller."
        )
    if not (1 <= DISCOVERY_PORT <= 65535 and 1 <= MANAGE_PORT <= 65535):
        raise RuntimeError("OMADA discovery/manage ports must be between 1 and 65535")
    if TLS_CA_FILE and not Path(TLS_CA_FILE).expanduser().exists():
        raise RuntimeError(f"OMADA_TLS_CA_FILE does not exist: {TLS_CA_FILE}")
