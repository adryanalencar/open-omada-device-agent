# ADR 0003: Isolate OpenWrt behind outbound ports

- Status: accepted
- Date: 2026-08-24

OpenWrt is one infrastructure choice, not part of the application model. UCI
reconciliation implements a configuration port under `adapters.outbound` and
is selected in the composition root. Commands use argv rather than
controller-derived shell strings. Other platform implementations can replace
it without changing application or domain code.
