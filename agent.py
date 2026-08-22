"""Backward-compatible launcher for running directly from a source checkout.

Prefer `open-omada-agent` after installing the project, or
`python -m open_omada_device_agent` from a development environment.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from open_omada_device_agent.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
