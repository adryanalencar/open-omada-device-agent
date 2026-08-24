"""Compatibility façade for host capability detection."""
from .application.contracts import PlatformCapabilities  # noqa: F401
from .adapters.outbound.openwrt.capabilities import *  # noqa: F403
