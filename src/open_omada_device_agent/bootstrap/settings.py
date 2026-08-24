"""Immutable settings passed from the environment boundary into the runtime."""
from dataclasses import dataclass
from pathlib import Path

from .. import config


@dataclass(frozen=True)
class AgentSettings:
    controller_host: str
    discovery_port: int
    manage_port: int
    state_file: Path
    tls_ca_file: Path | None = None

    @classmethod
    def from_environment(cls) -> "AgentSettings":
        """Snapshot legacy environment configuration once at composition time."""
        return cls(
            controller_host=config.CONTROLLER_HOST,
            discovery_port=config.DISCOVERY_PORT,
            manage_port=config.MANAGE_PORT,
            state_file=Path(config.STATE_FILE).expanduser(),
            tls_ca_file=Path(config.TLS_CA_FILE).expanduser() if config.TLS_CA_FILE else None,
        )

    def validate(self) -> None:
        if not self.controller_host:
            raise RuntimeError("OMADA_CONTROLLER_HOST is required")
        if not (1 <= self.discovery_port <= 65535 and 1 <= self.manage_port <= 65535):
            raise RuntimeError("OMADA discovery/manage ports must be between 1 and 65535")
        if self.tls_ca_file is not None and not self.tls_ca_file.exists():
            raise RuntimeError(f"OMADA_TLS_CA_FILE does not exist: {self.tls_ca_file}")
