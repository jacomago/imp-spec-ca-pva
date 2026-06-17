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
src/harness/      pure-Python library (normalform.py, io.py, golden.py)
adapters/         containerized implementations (adapters/ca/ — the CA DBR codec)
schemas/          JSON Schemas: normal form + adapter I/O + golden fixtures
fixtures/         golden fixtures — spec hex + hand-verified decoding (oracle v1)
docs/             sub-specs (normal-form.md, fixtures.md)
tests/            pytest: round-trips, schema validation, I/O loop, fixtures
```

## Ground truth

[`fixtures/`](fixtures/) holds **golden fixtures**: EPICS spec hex examples each
paired with a hand-verified decoding and a citation. They are the adjudicator
(oracle v1) that turns "implementations disagree" into "the spec says X," and
are authored from the spec hex — never snapshotted from an implementation. See
[`docs/fixtures.md`](docs/fixtures.md). CA fixtures arrive with the CA adapter
(Phase 0c).

## Install & test

```sh
pip install -e ".[dev]"
pytest -q
```

## How to add an adapter

An adapter is one participant in the [adapter contract](#the-three-contracts):
it reads JSON Lines **requests** on stdin and writes JSON Lines **responses** on
stdout, decoding values into the [normal form](docs/normal-form.md) and recording
serialized bytes as hex. The harness never imports an adapter — it runs each one
in its own container and talks over stdin/stdout — so adding an implementation is
purely additive.

The CA DBR adapter ([`adapters/ca/`](adapters/ca/)) is the worked example.

**1. Implement a `handler`.** Map a [`harness.io.Request`](src/harness/io.py) to a
`Response` and let [`harness.io.run_adapter`](src/harness/io.py) drive the
stdin/stdout loop (it validates every request and response against
[`schemas/adapter-io.schema.json`](schemas/adapter-io.schema.json) and turns any
exception into a clean `error` response):

```python
# adapters/ca/adapter.py (abridged)
def handler(request: io.Request) -> io.Response:
    if request.operation == "serialize":
        node = type_from_json(request.type)
        data = codec.serialize(node, io.decode_value(node, request.value))
        result = io.serialize_result(data.hex())
    else:  # deserialize
        node = type_from_json(request.type)
        native = codec.deserialize(node, bytes.fromhex(request.bytes_hex or ""))
        result = io.deserialize_result(node.to_json(), io.encode_value(node, native))
    return io.Response(request.case_id, request.operation, ADAPTER, result=result)

def main() -> None:
    io.run_adapter(ADAPTER, handler)
```

**2. Structure the package.** The CA adapter keeps the codec separate from the
wiring: [`codec.py`](adapters/ca/codec.py) (serialize/deserialize),
[`dbr.py`](adapters/ca/dbr.py) and [`mapping.py`](adapters/ca/mapping.py) (the
type model), [`adapter.py`](adapters/ca/adapter.py) (`handler` + provenance), and
[`__main__.py`](adapters/ca/__main__.py) so the container entry point is
`python -m ca`. Ship a small seed corpus too
([`corpus/seed.jsonl`](adapters/ca/corpus/seed.jsonl)).

**3. Record provenance.** Set `AdapterInfo.extra` to whatever pins the result —
library versions, codec notes. The differential report is only meaningful against
known versions. The CA adapter's codec is pure `ctypes`, so it records
`{"codec": "pure-ctypes", "pyepics": …, "epics_base": …}`; the version fields are
read best-effort and are `null` outside the container.

**4. Containerize with pinned, prebuilt dependencies.** Per the CI design, install
implementations from a package manager (conda-forge here) — never build EPICS from
source per run — and pin the versions.
[`adapters/ca/Dockerfile`](adapters/ca/Dockerfile) installs `epics-base` +
`pyepics` from conda-forge on a miniforge base, and its `ENTRYPOINT` is the adapter
itself:

```sh
docker build -f adapters/ca/Dockerfile -t ca-adapter .
docker run --rm -i ca-adapter < adapters/ca/corpus/seed.jsonl   # corpus -> artifacts
```

**5. Verify against the golden fixtures.** The pure-`ctypes` codec is tested in
the repo's pure-Python CI ([`tests/test_ca_adapter.py`](tests/test_ca_adapter.py))
against every CA fixture: serialize → bytes match, deserialize → value match, and
round-trip. Checks that need the real library live in
[`tests/test_ca_epics.py`](tests/test_ca_epics.py), guarded by
`pytest.importorskip("epics")` so they **skip** in pure-Python CI and **run** in
the container — where they also cross-check the `ctypes` layouts against libca's
own `dbr_size` table. The container runs the whole suite via
`docker run --rm --entrypoint pytest ca-adapter -q` (the non-blocking
[`ca-container.yml`](.github/workflows/ca-container.yml) workflow).

## References

Authoritative EPICS specs the harness conforms to:

- **CA:** [Channel Access Protocol Specification](https://docs.epics-controls.org/en/latest/internal/ca_protocol.html)
- **PVA:** [pvAccess Protocol Specification](https://docs.epics-controls.org/en/latest/pv-access/protocol.html) ·
  [Data Encoding](https://docs.epics-controls.org/en/latest/pv-access/Protocol-Encoding.html) (Size, scalars, `FieldDesc`, value codec) ·
  [Normative Types](https://docs.epics-controls.org/en/latest/pv-access/Normative-Types-Specification.html)
