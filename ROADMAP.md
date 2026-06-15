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

### Phase 0 — Skeleton + ground truth
Split into three sequentially-mergeable parts. 0a is a prerequisite for 0b and
0c; 0b and 0c are independent of each other.

Locked decisions: harness/consumer is pure Python (no EPICS deps); the first CA
adapter is pyepics/libca, containerized with EPICS base; no CI fan-out or Pages
yet (that is Phase 1).

**0a — Repo skeleton + normal-form sub-spec (contract #2).**
- Repo scaffolding (pure-Python `pyproject.toml`, package layout, README stub).
- The normal-form sub-spec: f64 hazard (int64/uint64 and out-of-±2^53 values as
  strings), explicit NaN/±inf, typed scalars (type+width+signedness), and
  empty-array vs empty-string vs null kept distinct; bytes as hex.
- JSON Schemas (normal form + the adapter stdin/stdout I/O contract) and the
  shared `harness/` library (`normalform.py`, `io.py`).

**0b — Golden fixtures (ground truth).**
- Encode the spec's authoritative hex examples as golden fixtures (timeStamp_t,
  the 243-byte structure, Status, BitSet), each pairing the exact spec hex with
  a hand-verified normal-form decoding and a cited source. These anchor every
  later adjudication.

**0c — One CA adapter (pyepics/libca, containerized).**
- An offline DBR `serialize`/`deserialize` adapter proving the adapter contract
  end to end. libca exposes no offline codec, so the adapter mirrors EPICS base
  `dbr.h` struct layouts via `ctypes` (no network); pyepics pins the EPICS base
  version in the provenance record.
- Dockerfile (EPICS base + pyepics, pinned versions); a small set of
  hand-verified CA DBR byte anchors + a seed corpus (0b's PVA fixtures do not
  apply to CA). Fills in the README "how to add an adapter" section.

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
- PVA adapters via pvxs and core-pva using their **offline** serialize/
  deserialize (sidesteps the stateful connection/registry-id problem entirely).
- Grow the corpus toward the edge cases: null struct-array elements (presence
  byte), variant union wrapping a structure, `Size` 253/254 boundary, bounded
  array at and over bound, partial-structure BitSet updates, unsigned extremes,
  multi-byte UTF-8, both endiannesses.

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
