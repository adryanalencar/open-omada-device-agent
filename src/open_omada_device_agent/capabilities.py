"""Conservative ECSP V2 capabilities advertised by the fake EAP.

The controller intersects this map with its own component table during
DEVICE_NEGOTIATION.  Advertising an empty ``components_v2`` map causes the
controller to build an invalid ComponentInfo and mark the AP incompatible.

Keep this baseline intentionally small: every version below was observed in
Controller 6.2.14.11's SYSTEM_NEGOTIATION response.  More AP capabilities can
be added incrementally as their SET/GET/INFORM behavior is implemented.
"""
from __future__ import annotations


AP_COMPONENTS_V2: dict[str, str] = {
    # Core managed-device lifecycle/config synchronization.
    "system": "2.0",
    "configVersion": "1.0",
    "time": "1.0",
    "informInterval": "1.2",
    "devInform": "2.0",
}


def ap_components_v2() -> dict[str, str]:
    """Return a copy so callers cannot mutate the module-level baseline."""
    return dict(AP_COMPONENTS_V2)
