# Golden fixtures (oracle v1)

Golden fixtures are the project's **ground truth**. Each pairs an EPICS spec's
authoritative hex example with a **hand-verified** decoding and a citation. When
independent implementations disagree, the fixtures are the adjudicator the
[roadmap](../ROADMAP.md) calls oracle v1 — they say which (if either) matches
the spec.

They are authored **from the spec hex**, never snapshotted from an
implementation's output (that would let an implementation define truth). There
is no PVA/CA codec in this repo yet — the [Kaitai CA decoder](../ROADMAP.md)
arrives in Phase 2 and the PVA value walker in Phase 4 — so the
hex↔decoding link is established by hand and by citation. The
[loader](../src/harness/golden.py) and [`tests/test_golden.py`](../tests/test_golden.py)
check everything *around* that link (see [Validation](#what-is-validated)).

Fixtures live at the repo root under `fixtures/<protocol>/<case>.json`, one
example per file, and are validated against
[`schemas/fixture.schema.json`](../schemas/fixture.schema.json).

## Envelope

```jsonc
{
  "case_id": "pva.introspection.timestamp", // unique, dotted, [a-z0-9_.]
  "protocol": "pva",                         // "pva" | "ca" (CA fixtures: Phase 0c)
  "byte_order": "little",                    // endianness the bytes are in
  "source": {                                // citation — every fixture is sourced
    "spec": "pvAccess Data Encoding",
    "url":  "https://docs.epics-controls.org/.../Protocol-Encoding.html",
    "section": "Introspection data — Example 1 (timeStamp_t), size = 57",
    "note": "…how the bytes decode / any subtlety…"
  },
  "segments": {                              // the exact spec bytes (≥1 of these)
    "introspection_bytes_hex": "FD 00 01 80 …", // FieldDesc (type) bytes
    "value_bytes_hex":         "…",             // value bytes
    "meta_bytes_hex":          "01 17"          // BitSet / Status compact form
  },
  "decoded": { /* one of the three shapes below */ }
}
```

Hex may be written with the spaces the spec uses for grouping; the loader
canonicalizes (whitespace stripped, lower-cased) before converting to bytes.

### Why segments, not one `bytes_hex`

PVA serializes the **type** (a `FieldDesc`) and the **value** as separate byte
runs, and BitSet / Status are compact **meta-encodings** rather than generic
struct encodings. A fixture records whichever segment(s) its example provides —
an introspection example carries only `introspection_bytes_hex`, a BitSet only
`meta_bytes_hex`, and an example that shows both a `FieldDesc` and its matching
value carries both.

### The three `decoded` shapes

| shape | when | content |
|-------|------|---------|
| **introspection** | FieldDesc-only example | `{ "type": <TypeNode> }` — anchors a [type tree](normal-form.md) (no value) |
| **document** | value / full-message example | a complete normal-form document `{ "schema_version":"0a", "type":…, "value":… }` |
| **meta** | BitSet / Status | `{ "meta": { "kind": "bitset"\|"status", … } }` |

`meta.bitset` carries `indices` (the set bits, ascending). `meta.status`
carries `type` (`OK`/`WARNING`/`ERROR`/`FATAL`), `message`, and `call_tree`.
BitSet and Status have no first-class normal-form node yet; modelling them under
`meta` keeps the fixture honest rather than forcing a shape the normal form does
not define.

## What is validated

[`tests/test_golden.py`](../tests/test_golden.py) asserts, over every fixture:

1. **shape** — validates against `fixture.schema.json`;
2. **conformance** — a `document` decoding passes `normalform.validate`
   (type↔value) and the normal-form schema; an `introspection` type tree parses
   via `normalform.type_from_json`;
3. **round-trip idempotence** — a `document` decoding survives
   `decode_document` → `document` unchanged, guarding the hand decoding against
   encoding-rule slips (e.g. a width-64 int written as a number);
4. **well-formed hex** — every segment is even-length hex;
5. **unique `case_id`s.**

What it deliberately does **not** do is mechanically re-derive the decoding from
the bytes — there is no decoder yet, and that is the point of a golden fixture.
In Phase 2/4 the Kaitai and spec-derived adapters must *reproduce* these
fixtures; that is where the hex↔decoding link gets machine-checked.

## Current fixtures (PVA)

- `pva.introspection.timestamp` — the 57-byte `timeStamp_t` `FieldDesc`.
- `pva.bitset.*` — empty, `{0}`, `{1}`, `{7}`, `{0,1,2,4}`.
- `pva.status.ok`, `pva.status.warning` — the `0xFF` OK shortcut and a WARNING
  with message.

### Deferred (need exact hex from a primary source)

The published encoding page truncates two long examples with `…`, so their
exact bytes cannot be transcribed reliably and they are **not** included yet:

- the **243-byte `exampleStructure`** `FieldDesc` (introspection), and
- the **264-byte Status ERROR** example (with call tree).

The user-data **value** "Encoding Example" is likewise pending — it needs its
matching `FieldDesc` and a careful hand-walk before it can be a trustworthy
anchor. Add these once transcribed byte-for-byte from the official pvAccess
specification PDF.

## Sources

- [pvAccess Data Encoding](https://docs.epics-controls.org/en/latest/pv-access/Protocol-Encoding.html)
  — Size, scalars, `FieldDesc` type codes, BitSet, Status.
- [EPICS V4 Normative Types](https://docs.epics-controls.org/en/latest/pv-access/Normative-Types-Specification.html)
  — `timeStamp_t` and other conventional shapes.
