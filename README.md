# ca-pva-machine-spec

A conformance test harness for EPICS **Channel Access** and **pvAccess** that
grows, over time, into a machine-readable specification. The test suite is the
durable core; the spec is distilled from it. See [`ROADMAP.md`](ROADMAP.md) for
the full plan.

This repository is **pure Python with no EPICS dependencies** — it is the
dependency-light core that the conformance consumer and every adapter build on.
(Implementations such as pyepics/pvxs/core-pva are containerized adapters, added
in later phases.)

## Two protocols, one normal form

EPICS has two wire protocols, with very different data models — keeping them
distinct matters throughout this repo:

- **Channel Access (CA)** — the older protocol. Its data is the fixed **DBR**
  family of types (`DBR_STRING`, `DBR_SHORT`, `DBR_FLOAT`, `DBR_ENUM`,
  `DBR_CHAR`, `DBR_LONG`, `DBR_DOUBLE`) with static layouts. No self-describing
  type information travels with the data.
- **pvAccess (PVA)** — the EPICS 7 protocol. Its data is **pvData**: a
  self-describing `FieldDesc` type grammar plus a type-directed value codec
  (structs, unions, variants, bounded arrays), with conventional shapes defined
  by the Normative Types.

Both decode into the **same normal form** (contract #2): a type tree + a value
tree. CA's DBR types map onto the scalar/array part of the grammar; PVA's
`FieldDesc` exercises the full grammar. The precise CA-DBR → type-tree mapping
(including `DBR_ENUM` and the DBR metadata fields) is pinned down with the CA
adapter in Phase 0c. See [`docs/normal-form.md`](docs/normal-form.md) and the
[references](#references) below.

## The three contracts

Everything plugs into three stable contracts:

1. **Adapter contract** — every participant exposes, offline and with no
   network: `serialize(value_spec) -> bytes` and
   `deserialize(bytes, fielddesc?) -> value_tree`. Adapters run in their own
   container and talk over stdin/stdout. Wire form:
   [`harness.io`](src/harness/io.py) +
   [`schemas/adapter-io.schema.json`](schemas/adapter-io.schema.json).
2. **Canonical normal form** — one normalized representation for a decoded value
   tree, emitted by every adapter. Spec:
   [`docs/normal-form.md`](docs/normal-form.md); implementation:
   [`harness.normalform`](src/harness/normalform.py); grammar:
   [`schemas/normal-form.schema.json`](schemas/normal-form.schema.json).
3. **Pluggable oracle** — the "reference" slot is swappable, so strengthening
   the oracle never requires a rewrite (later phases).

## Layout

```
src/harness/      pure-Python library (normalform.py, io.py)
schemas/          JSON Schemas: normal form + adapter I/O contract
docs/             sub-specs (normal-form.md)
tests/            pytest: round-trips, schema validation, I/O loop
```

## Install & test

```sh
pip install -e ".[dev]"
pytest -q
```

## How to add an adapter

> _Stub — filled in by Phase 0c (the first CA adapter, pyepics/libca,
> containerized)._ An adapter reads JSON Lines requests on stdin and writes JSON
> Lines responses on stdout. Implement a `handler(request) -> Response` and run
> it through [`harness.io.run_adapter`](src/harness/io.py), reporting decoded
> values in the [normal form](docs/normal-form.md) and serialized bytes as hex.

## References

Authoritative EPICS specs the harness conforms to:

- **CA:** [Channel Access Protocol Specification](https://docs.epics-controls.org/en/latest/internal/ca_protocol.html)
- **PVA:** [pvAccess Protocol Specification](https://docs.epics-controls.org/en/latest/pv-access/protocol.html) ·
  [Data Encoding](https://docs.epics-controls.org/en/latest/pv-access/Protocol-Encoding.html) (Size, scalars, `FieldDesc`, value codec) ·
  [Normative Types](https://docs.epics-controls.org/en/latest/pv-access/Normative-Types-Specification.html)
