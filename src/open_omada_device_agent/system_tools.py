"""Host telemetry helpers for the reference device profile."""
from __future__ import annotations

import time

import psutil


def get_system_uptime() -> int:
    """Return host uptime in seconds."""
    return max(0, int(time.time() - psutil.boot_time()))


def get_memory_utilization() -> float:
    """Return host memory utilization as a percentage."""
    return round(float(psutil.virtual_memory().percent), 1)


def get_cpu_utilization() -> float:
    """Return non-blocking host CPU utilization as a percentage."""
    return round(float(psutil.cpu_percent(interval=None)), 1)
