# ADR 0001: Bounded contexts and explicit ports

- Status: accepted
- Date: 2026-08-24

## Context

The flat package made adoption responsible for protocol, configuration,
platform commands, clients, portal, persistence, and informs. Extending device
families would multiply conditionals in the central session.

## Decision

Organize domain concepts by device, lifecycle, wireless, networking, clients,
and portal contexts. Application use cases define structural ports. Concrete
platform dependencies are wired in a small composition root. Keep temporary
compatibility façades so protocol behavior can migrate incrementally.

## Consequences

Domain behavior is testable without OpenWrt and the managed session no longer
constructs configuration adapters. Some flat façades and collectors remain
until callers migrate; architecture tests prevent dependencies from turning
outward again.
