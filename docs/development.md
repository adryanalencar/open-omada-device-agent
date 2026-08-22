# Development Guide

## Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

## Tests

```bash
pytest
```

The current tests cover:

- length-prefixed ECSP framing;
- key message type values;
- legacy authentication calculations;
- first-adoption and managed-reconnect body shapes;
- conservative capability advertisement;
- managed informs;
- absolute and incremental SET config version handling;
- state persistence without password material;
- managed rediscovery identity.

## Lint

```bash
ruff check .
```

## Run from source

```bash
cp .env.example .env
open-omada-agent --dump-tx
```

Use a dedicated lab controller. The `--dump-tx` option logs complete ECSP JSON
and may expose operational metadata, so sanitize logs before sharing them.

## Adding a message family

A suggested implementation sequence is:

1. add or verify the numeric message type in `ecsp.py`;
2. capture a minimal request/response pair;
3. create a body validator/model;
4. implement a handler without over-acknowledging unsupported behavior;
5. add tests;
6. update `protocol-status.md`;
7. advertise the corresponding component only when appropriate.
