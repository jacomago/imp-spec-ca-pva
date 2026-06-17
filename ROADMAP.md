# ca-pva-machine-spec — Roadmap

A conformance test harness for EPICS Channel Access and pvAccess that grows,
over time, into a machine-readable specification. The test suite is the durable
core; the spec is distilled from it.

## Scope boundary (decide this first)

**Committed (v1):** data-encoding conformance and a machine-readable spec for
the *data* layers — all of CA, and pvData layers 0–2 (Size/scalars/string/bitset,
the `FieldDesc` type grammar, and the type-directed value codec).

**Stretch / research track (parallel, non-blocking):** a formal description of
PVA layer 3 (connection state machine, registries, endianness negotiation);
multi-language code generation from the spec; property-based corpus generation.

Layer 3 is a *state-machine* problem, not a data-encoding one — a different
formalism (e.g. session/state-chart description), and not on the critical path.
Real implementations (pvxs, core-pva) host layer 3 during testing.

---

## Invariant architecture (build this on day one; it does not change)

Three contracts everything else plugs into:

### 1. Adapter contract
The harness never references a specific implementation. It knows only:

```
serialize(value_spec)            -> bytes        # offline, no network
deserialize(bytes, fielddesc?)   -> value_tree   # offline, no network
```

Every participant is an adapter: pvxs, core-pva, the Kaitai-generated decoder,
and later the spec-derived decoder. Adding a participant = adding an adapter.

Run adapters in their own containers; communicate via stdin/stdout files
(corpus in, artifacts out). No shared process, no shared language.

### 2. Canonical normal form
One normalized representation for a decoded value tree, emitted by every adapter.
Pitfalls to pin down in this sub-spec (it is load-bearing):
- JSON numbers are f64: encode int64/uint64 (and any value outside ±2^53) as
  strings.
- Represent NaN / ±inf explicitly (JSON has no native form).
- Tag scalar type + width + signedness; plain JSON blurs `int` vs `long` vs
  `uint`.
- Distinguish empty array, empty string, and null (PVA treats these differently).
Serialized bytes are recorded as a hex string.

### 3. Pluggable oracle
The "reference" slot is swappable. This is what makes the test direction
reversible without rework — there is no separate "reverse the tests" step, only
a stronger oracle dropped into the same harness:

```
oracle v0:  consensus of independent implementations
oracle v1:  + golden fixtures (spec hex examples)        <- adjudicates disagreements
oracle v2:  + Kaitai-derived reference decoder
oracle v3:  + full spec-derived reference decoder        <- "spec vs implementations"
```

The two verdicts per comparison are kept separate:
- **semantic match** (decoded trees equal) — a failure is an interop bug.
- **byte-identical** (serializations equal) — a failure is often a legitimate
  degree of freedom (caching, BitSet trailing-zero trimming, which `Size` form);
  cataloguing these is a primary research output.

---

## Phases

Status legend: ✅ done · 🚧 in progress · ⬜ not started

### Phase 0 — Skeleton + ground truth  (🚧 in progress)
Three sequentially-mergeable parts: 0a (a prerequisite for both), then 0b and 0c,
which are independent of each other. 0c is itself split into 0c-1…0c-3 (below).

Locked decisions: harness/consumer is pure Python (no EPICS deps); the first CA
adapter is pyepics/libca, containerized with EPICS base + pyepics from conda-forge;
no CI fan-out or Pages yet (that is Phase 1).

**0a — Repo skeleton + normal-form sub-spec (contract #2).  ✅ Done (PR #1).**
- Repo scaffolding (pure-Python `pyproject.toml`, package layout, README stub).
- The normal-form sub-spec: f64 hazard (int64/uint64 and out-of-±2^53 values as
  strings), explicit NaN/±inf, typed scalars (type+width+signedness), and
  empty-array vs empty-string vs null kept distinct; bytes as hex.
- JSON Schemas (normal form + the adapter stdin/stdout I/O contract) and the
  shared `harness/` library (`normalform.py`, `io.py`).

**0b — Golden fixtures (ground truth).  ✅ Done (PR #2).**
- Encode the spec's authoritative hex examples as golden fixtures, each pairing
  the exact spec hex with a hand-verified decoding and a cited source. These
  anchor every later adjudication (oracle v1).
- Fixture envelope (`schemas/fixture.schema.json`), loader (`harness/golden.py`),
  and sub-spec (`docs/fixtures.md`). Shipped PVA fixtures: the 57-byte
  `timeStamp_t` `FieldDesc`, the BitSet set (∅/{0}/{1}/{7}/{0,1,2,4}), and
  Status OK/WARNING.
- Deferred (truncated with `…` in the published spec, need byte-exact
  transcription from the primary-source PDF): the 243-byte `exampleStructure`
  `FieldDesc`, the 264-byte Status ERROR example, and the user-data value
  example. Tracked in `docs/fixtures.md`.

**0c — One CA adapter (pyepics/libca, containerized).  🚧**
Proves the adapter contract end to end on CA's static DBR data. libca exposes no
offline codec, so the adapter mirrors EPICS base `dbr.h` struct layouts via
`ctypes` (no network). Split into three sequentially-mergeable parts: 0c-1 is a
prerequisite for 0c-2, and 0c-3 depends on 0c-2.

- **0c-1 — CA-DBR → normal-form mapping + CA golden fixtures.  ✅** Pure Python,
  no EPICS. Pin the CA-DBR → type-tree mapping in `docs/normal-form.md`: the seven
  base types (incl. `DBR_ENUM` → the raw enum index) and the `DBR_STS_*` /
  `DBR_TIME_*` metadata variants (status/severity/timestamp as struct fields; the
  `RISC_pad` alignment bytes are a byte-identical degree of freedom, not value-tree
  fields). Add the hand-verified CA DBR byte anchors as golden fixtures under
  `fixtures/ca/` (`documentDecoded` shape, `protocol:"ca"`, `byte_order:"big"`).
  No schema or `normalform` change is needed — the existing `tests/test_golden.py`
  covers them in CI. This extends the golden-fixture oracle (v1) to CA and unblocks
  the adapter.
- **0c-2 — CA DBR offline codec adapter.  ✅** The first concrete adapter, under
  `adapters/ca/`: `ctypes.BigEndianStructure` mirrors of `dbr.h` (including the
  explicit `RISC_pad` fields), a bijective DBR-code ↔ normal-form `TypeNode`
  mapping, `serialize`/`deserialize` driven by `harness.io.run_adapter`, and a seed
  corpus (`adapters/ca/corpus/seed.jsonl`; 0b's PVA fixtures do not apply to CA).
  The codec is pure `ctypes` (no network, no libca) and tested in pure-Python CI
  against every 0c-1 fixture. pyepics is an optional dependency read only for the
  provenance record (`extra`); recorded as `null` here, pinned for real in the
  0c-3 container.
- **0c-3 — Containerize + provenance + "how to add an adapter".  ✅** Dockerfile
  (`adapters/ca/Dockerfile`) on a miniforge base installing pinned `epics-base` +
  pyepics from **conda-forge** — not built from source; both versions are read
  back into the adapter's provenance `extra` at runtime (`adapter.py`
  `_provenance` / `_epics_base_version`). Container-run tests
  (`tests/test_ca_epics.py`, guarded by `importorskip("epics")` so they skip in
  pure-Python CI) reproduce every 0c-1 fixture (serialize → bytes match,
  deserialize → value match) **and** cross-check the `ctypes` DBR layouts against
  libca's own `dbr_size` table — the "machine-verified against real EPICS" the CA
  fixtures promise. They run in the image via a separate non-blocking workflow
  (`.github/workflows/ca-container.yml`), not the blocking pure-Python CI. The
  README "how to add an adapter" section is filled in using this adapter as the
  worked example.

### Phase 1 — CA differential harness (the pipeline shakedown)
CA data is static (DBR), so this is "Kaitai + diff" and is where you get the
whole pipeline working on the *easy* protocol.
- Two independent CA adapters; corpus of CA messages/values.
- Producer/consumer CI (see below); report published to GitHub Pages.
- README with project intent and how to add an adapter.

### Phase 2 — CA spec-derived reference
- Kaitai `.ksy` for CA (header, extended header, DBR payloads).
- Register the Kaitai decoder as another adapter; it must pass the Phase-1
  corpus. Promote it toward the oracle (v2).

### Phase 3 — PVA data harness (the hard corpus work)
This is where the real difficulty lives — treat it as its own effort, not
"same as CA."
- **Prerequisite — finish union/variant in the normal form (see below).**
- PVA adapters via pvxs and core-pva using their **offline** serialize/
  deserialize (sidesteps the stateful connection/registry-id problem entirely).
  This is the first **Java** dependency: the core-pva adapter container pulls
  core-pva from Maven / Phoebus releases (conda-forge supplying only the JVM), per
  the dependency-sourcing principle in the CI design.
- Grow the corpus toward the edge cases: null struct-array elements (presence
  byte), variant union wrapping a structure, `Size` 253/254 boundary, bounded
  array at and over bound, partial-structure BitSet updates, unsigned extremes,
  multi-byte UTF-8, both endiannesses.

> **Pre-Phase-3 prerequisite — union/variant value support.** The normal-form
> *grammar* already reserves `union` and `variant` type nodes
> (`schemas/normal-form.schema.json`, documented in `docs/normal-form.md`), but
> the `0a` Python implementation does **not** model them: `type_from_json`
> rejects any kind beyond scalar/array/struct, and `encode_value`/`decode_value`
> have no union/variant case. A fixture using a union therefore passes JSON
> Schema validation but fails the loader. Phase 3's corpus explicitly needs
> "variant union wrapping a structure," so before that corpus can be authored
> the type tree and value walker must gain: (a) `type_from_json` parsing of
> `union`/`variant`; (b) a value encoding for a union (selected member +
> value) and a variant (a self-describing `{type, value}` cell); and (c) a
> `schema_version` bump past `0a` once the value-tree shape is fixed. This is a
> discrete, self-contained unit of work that gates Phase 3 (and the deferred
> 0b `exampleStructure` fixture if its transcription turns out to contain a
> union), and is not otherwise on any phase's checklist.

### Phase 4 — PVA layers 0–2 as an adapter
- Kaitai for layers 0–1 (FieldDesc grammar) + the value walker for layer 2
  (from the meta-format draft). Layer 3 hosted by pvxs/core-pva.
- Register as an adapter; must pass the Phase-3 corpus.

### Phase 5 — Flip the oracle to the spec
- Once the derived decoder passes the corpus, designate it the reference.
- Comparisons now read as "implementations vs spec." No rewrite — just an
  oracle swap (contract #3).

### Research track (parallel, optional)
- Property-based corpus generation (random valid Field trees + values).
- Multi-language codegen from the meta-format catalog.
- Formal layer-3 (state-machine) description.

---

## CI design (the part that gets complicated)

Fan-out producers → artifacts → one dependency-light consumer.

```
[corpus] --> (matrix) producer job per (implementation x corpus)
                 |  runs in that impl's prebuilt container
                 |  emits: trees as typed JSON, bytes as hex
                 v
           upload artifacts
                 |
                 v
        consumer job (pure Python, NO EPICS deps)
           diff trees (semantic) + diff bytes (byte-identical)
           render conformance matrix + disagreements view
                 |
                 v
        publish static report to GitHub Pages
```

Principles:
- **Containerize implementations; never build EPICS base from scratch per run.**
  Prebuild and publish images (epics-base+pvxs; Phoebus core-pva; etc.).
- **Use conda (conda-forge) for Python and C/C++ dependencies where possible.**
  EPICS base, pvxs, pyepics and friends ship as conda-forge packages, so adapter
  images install pinned binaries instead of compiling from source — faster,
  reproducible, and the pinned package versions feed straight into the provenance
  record. The pure-Python harness core stays pip/`pyproject.toml` with no EPICS
  deps; conda is for the adapter containers. Where conda is not the idiomatic
  source, use the ecosystem's package manager instead — e.g. the Java `core-pva`
  adapter (Phase 3) pulls core-pva from Maven / Phoebus releases (conda-forge only
  supplying the JVM, `openjdk`). Whatever the source, pin the versions and record
  them in the adapter's provenance.
- **The publish path has zero toolchain dependencies** — the consumer is plain
  Python reading files, so reporting never breaks because a C++ build broke.
- **No live networking in blocking CI** — all data tests are offline. Live
  interop is a separate, non-blocking job allowed to be flaky.
- **Pin and record implementation versions** in every report; differential
  results are only meaningful against known versions.
- **Two testing layers, two tools.** Conformance comparison is *not* an xUnit
  job — its output is a 3-valued matrix where byte-mismatches are catalogued
  degrees of freedom, not failures. So:
  - **`pytest`** runs conventional unit/fixture tests (normal-form round-trips,
    schema validation, adapter round-trips) and a thin *gating* layer that reads
    the engine's results and asserts the subset that must hold (e.g. a promoted
    adapter must semantic-match the whole corpus).
  - a **pure-Python conformance engine** (the consumer above) owns the matrix:
    it reads artifacts, computes both verdicts, and emits JSON results + the
    static report. It is decoupled from pass/fail so reporting never breaks
    because a test failed.
  - Fixtures stay **hand-authored from the spec hex** — no auto-snapshot tools
    (`syrupy` et al.), which would let an implementation's output define truth.

The report headlines **disagreements**: a matrix of corpus-case ×
implementation × {semantic-match, byte-identical, fail}, with divergences
surfaced as candidate spec ambiguities. That view is the project's contribution
independent of the spec.

---

## Risks and how the design absorbs them

| Risk | Mitigation |
|------|------------|
| Differential testing finds disagreement, not truth | Golden fixtures (Phase 0) as adjudicator; spec hex examples are authoritative |
| Implementations not actually independent | Pair across lineages (C++ pvxs vs Java core-pva); avoid pairs sharing a serializer |
| CI brittleness from multi-toolchain builds | Containerized producers + dependency-light consumer; offline only in blocking CI |
| Layer 3 sprawl swallowing the project | Layer 3 explicitly off critical path; hosted by real impls; formal version is stretch |
| "Reverse the tests" requiring a rewrite | Pluggable oracle — direction is an oracle swap, not a rewrite |
| Corpus underfeeding the harness | Treat corpus as the deliverable; hand-authored first, property-based later |

---

## References — authoritative specs

These are the sources the harness conforms to. Fixtures and ambiguity reports
cite the relevant one.

**Channel Access (CA)** — the older protocol; data is the static **DBR** family
(`DBR_STRING/SHORT/FLOAT/ENUM/CHAR/LONG/DOUBLE`).
- [Channel Access Protocol Specification](https://docs.epics-controls.org/en/latest/internal/ca_protocol.html)

**pvAccess (PVA)** — the EPICS 7 protocol; data is **pvData**: a self-describing
`FieldDesc` type grammar plus a type-directed value codec, with conventional
shapes defined by the Normative Types.
- [pvAccess Protocol Specification](https://docs.epics-controls.org/en/latest/pv-access/protocol.html)
- [pvAccess Data Encoding](https://docs.epics-controls.org/en/latest/pv-access/Protocol-Encoding.html) — Size, scalars, `FieldDesc`, value codec (the pvData layers 0–2 this project covers)
- [EPICS V4 Normative Types](https://docs.epics-controls.org/en/latest/pv-access/Normative-Types-Specification.html)
- [Protocol Messages Specification](https://docs.epics-controls.org/en/latest/pv-access/Protocol-Messages.html) — layer 3, off the critical path
