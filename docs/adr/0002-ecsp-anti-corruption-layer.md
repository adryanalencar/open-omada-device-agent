# ADR 0002: Treat ECSP as an anti-corruption layer

- Status: accepted
- Date: 2026-08-24

ECSP framing, legacy authentication, message identifiers, and controller JSON
mapping live under `adapters.inbound.ecsp`. Controller dictionaries are mapped
to typed context intents before application orchestration. Wire compatibility
façades remain temporarily. Domain code must not import ECSP.
