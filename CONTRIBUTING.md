# Contributing to Open Omada Device Agent

Thank you for helping improve open Omada interoperability.

## Principles

Contributions should be independently implemented, reproducible, and grounded
in observable protocol behavior. Please do not submit proprietary vendor source
code, decompiled source files, firmware images, private keys, certificates, or
confidential controller data.

When documenting a protocol field or state transition, label the evidence as
one of:

- **Observed** — directly seen on the wire or in controller/device output.
- **Validated** — reproduced in a controlled interoperability test.
- **Inferred** — strongly suggested by behavior but not yet independently proven.
- **Unknown** — field or behavior exists, but semantics are not established.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
ruff check .
```

## Pull requests

Keep protocol changes small enough to review. A good protocol PR normally
includes:

1. a short description of the observed behavior;
2. a test or reproducible lab procedure;
3. the implementation change;
4. documentation updates when the wire contract changes.

Do not include real controller addresses, account names, passwords, session
cookies, tokens, or production packet captures.

## Commit style

Conventional Commits are encouraged but not required. Examples:

```text
feat(protocol): handle incremental SET config versions
fix(reconnect): recover stale controller context with rediscovery
docs(ecsp): document PRE_CONNECT negotiation
```
