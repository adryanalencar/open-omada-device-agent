"""Network helpers used to build device telemetry."""
from __future__ import annotations

import logging
from functools import lru_cache
from urllib.error import URLError
from urllib.request import urlopen

from . import config

log = logging.getLogger("open_omada.network")


@lru_cache(maxsize=1)
def get_public_ip() -> str:
    """Return the IP address advertised in ECSP deviceInfo.

    The default is ``0.0.0.0``. Set ``OMADA_DEVICE_IP`` to a concrete value or
    to ``auto`` to enable a best-effort public-IP lookup.
    """
    configured = config.DEVICE_IP
    if configured.lower() != "auto":
        return configured or "0.0.0.0"

    try:
        with urlopen(  # noqa: S310 - the URL is explicitly operator-configured
            config.PUBLIC_IP_LOOKUP_URL,
            timeout=config.PUBLIC_IP_LOOKUP_TIMEOUT,
        ) as response:
            value = response.read(128).decode("ascii", errors="strict").strip()
            return value or "0.0.0.0"
    except (OSError, URLError, UnicodeError, ValueError) as exc:
        log.warning("Public-IP lookup failed: %s", exc)
        return "0.0.0.0"
