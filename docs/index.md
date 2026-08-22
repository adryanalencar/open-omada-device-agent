# Open Omada Device Agent Documentation

This documentation describes the protocol model and software architecture used
by Open Omada Device Agent.

## Guides

| Document | Purpose |
| --- | --- |
| [Protocol overview](protocol-overview.md) | High-level ECSP model and message families |
| [Wire format](ecsp-wire-format.md) | JSON envelope and 4-byte length framing |
| [Device lifecycle](device-lifecycle.md) | Discovery, adoption, authentication, sync, and reconnect |
| [Architecture](architecture.md) | Internal module boundaries and runtime data flow |
| [Configuration](configuration.md) | Environment variables and deployment guidance |
| [Protocol status](protocol-status.md) | Implemented and planned message families |
| [Research methodology](research-methodology.md) | Evidence model and clean-room documentation rules |
| [Development](development.md) | Tests, style, and contributor workflow |

## Scope

The current implementation focuses on a reference access-point profile and the
ECSP V2 family observed with Omada Network Application 6.2.x. It is not a claim
of complete compatibility with every Omada controller release or device family.

The project is intentionally conservative: a message family is advertised as
supported only when the device-side behavior is understood enough to avoid
acknowledging configuration that the agent cannot actually model.

## Diagram language

Protocol and lifecycle documentation favors Mermaid `sequenceDiagram` blocks so
that transport, direction, and message ordering are immediately visible. Static
software relationships use `flowchart`, while internal lifecycle states use
`stateDiagram-v2`.
