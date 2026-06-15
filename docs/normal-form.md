# The canonical normal form (contract #2)

This is the sub-spec for the **one normalized representation** every adapter
emits and every comparison reads. It is load-bearing: golden fixtures, adapter
artifacts, and the conformance engine all depend on it, so it is pinned down
here before anything is built on top.

A normal-form **document** is a pair of a *type tree* and a *value tree*:

```json
{ "schema_version": "0a", "type": <TypeNode>, "value": <ValueNode> }
```

The split mirrors PVA's own FieldDesc/value separation, which keeps Phase 4
(the layer-0/1 type grammar plus the layer-2 value walker) a natural extension
rather than a rewrite. The structural grammar is enforced by
[`schemas/normal-form.schema.json`](../schemas/normal-form.schema.json); the
**type↔value conformance check** (that a value actually matches its type) is not
expressible in JSON Schema and lives in
[`harness.normalform.validate`](../src/harness/normalform.py).

Serialized bytes are **not** part of the normal form. They are recorded as a hex
string in the adapter artifact / fixture envelope (see
[`schemas/adapter-io.schema.json`](../schemas/adapter-io.schema.json)).

## CA and PVA both land here

The normal form is protocol-agnostic on purpose — it is the common target for
both EPICS protocols, which have different data models:

- **Channel Access (CA)** carries the fixed **DBR** types
  (`DBR_STRING/SHORT/FLOAT/ENUM/CHAR/LONG/DOUBLE`). These map onto the
  `scalar` (and `array`) part of the type tree — e.g. `DBR_LONG` →
  `{kind:"scalar", type:"int", width:32, signed:true}`, `DBR_DOUBLE` →
  `{type:"float", width:64}`. The exact mapping for `DBR_ENUM` and the DBR
  metadata (status/severity/timestamp) fields is fixed alongside the CA adapter
  in Phase 0c.
- **pvAccess (PVA)** carries **pvData**, whose `FieldDesc` grammar exercises the
  full type tree, including `struct`, `union`, `variant`, and bounded arrays.

Because both decode into the same `{type, value}` document, an adapter for
either protocol is interchangeable to the rest of the harness.

## Type tree (`TypeNode`)

Every node carries a `kind`:

| kind | shape | notes |
|------|-------|-------|
| `scalar` | `{ "kind":"scalar", "type":"int\|float\|string\|boolean", "width":…, "signed":… }` | `width`+`signed` are required for `int` (width ∈ 8/16/32/64); `float` carries `width` ∈ 32/64 and no `signed`; `string`/`boolean` carry neither. |
| `array` | `{ "kind":"array", "element":<TypeNode>, "bound":null\|int }` | `bound` null = variable length; an integer reserves PVA fixed/bounded arrays. |
| `struct` | `{ "kind":"struct", "id"?:"…", "fields":[ {"name":…, "type":<TypeNode>}, … ] }` | **Field order is significant** and preserved everywhere. |
| `union`, `variant` | reserved | Present in the schema grammar for PVA (Phase 3). The 0a value walker does **not** implement union/variant values yet. |

Tagging type explicitly (type + width + signedness) is deliberate: plain JSON
blurs `int` vs `long` vs `uint`, and the harness needs those distinctions to
adjudicate disagreements.

## Value tree (`ValueNode`) — encoding rules

The value tree is plain JSON, encoded against its type with a few rules that
resolve JSON's lossy spots. These four hazards are the reason the normal form
exists:

### 1. The f64 hazard — large integers as strings

JSON numbers are IEEE-754 f64, which exactly represents integers only up to
±2^53.

- **int, width ≤ 32** → JSON **number**.
- **int, width 64** → JSON **string** (decimal, e.g. `"18446744073709551615"`).

A width test suffices: every ≤32-bit value (signed or unsigned) fits safely in
an f64, and only a 64-bit value can exceed 2^53. So this single rule subsumes
the more general "anything outside ±2^53 as a string."

### 2. Non-finite floats are explicit

JSON has no literal for NaN or infinities, so they are encoded as token
strings:

| native | encoded |
|--------|---------|
| finite | JSON number |
| NaN | `"nan"` |
| +∞ | `"inf"` |
| −∞ | `"-inf"` |

`width` (32 vs 64) comes from the type tree, not the value.

### 3. Typed scalars

`string` → JSON string; `boolean` → JSON bool. Their type/width come from the
type tree, never inferred from the JSON value.

### 4. `null` vs empty array vs empty string are distinct

PVA treats these as three different things, so the normal form keeps them
separate:

| meaning | encoded |
|---------|---------|
| null / absent (e.g. a missing struct-array element via a presence byte) | `null` |
| empty array | `[]` |
| empty string | `""` |

`null` is permitted at any position to represent an absent value.

## Composite values

- **array** → JSON array of encoded element values.
- **struct** → JSON **object** keyed by field name, in the type tree's field
  order.

## Worked example — `timeStamp_t`

```json
{
  "schema_version": "0a",
  "type": {
    "kind": "struct",
    "id": "timeStamp_t",
    "fields": [
      { "name": "secondsPastEpoch", "type": { "kind": "scalar", "type": "int", "width": 64, "signed": true } },
      { "name": "nanoseconds",      "type": { "kind": "scalar", "type": "int", "width": 32, "signed": false } },
      { "name": "userTag",          "type": { "kind": "scalar", "type": "int", "width": 32, "signed": true } }
    ]
  },
  "value": {
    "secondsPastEpoch": "1600000000",
    "nanoseconds": 123456789,
    "userTag": 0
  }
}
```

Note `secondsPastEpoch` (width 64) is a string while the 32-bit fields are
numbers.

## Two verdicts

Downstream comparisons keep two verdicts separate (see the roadmap):

- **semantic match** — decoded value trees equal. Implemented by
  `harness.normalform.semantic_equal` (NaN compares equal to NaN; finite floats
  compare by value). A failure here is an interop bug.
- **byte-identical** — serializations equal. Computed over the artifact's
  `bytes_hex`, *not* over the normal form. A failure here is often a legitimate
  degree of freedom and is catalogued, not treated as a hard failure.

## Sources

- [Channel Access Protocol Specification](https://docs.epics-controls.org/en/latest/internal/ca_protocol.html) — DBR types.
- [pvAccess Data Encoding](https://docs.epics-controls.org/en/latest/pv-access/Protocol-Encoding.html) — Size, scalars, `FieldDesc`, value codec (pvData layers 0–2).
- [EPICS V4 Normative Types](https://docs.epics-controls.org/en/latest/pv-access/Normative-Types-Specification.html) — conventional structure shapes (e.g. `timeStamp_t`).
