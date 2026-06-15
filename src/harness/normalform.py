"""Contract #2 — the canonical normal form.

A normal-form *document* is a pair::

    { "schema_version": "0a", "type": <TypeNode>, "value": <ValueNode> }

The **type tree** describes structure (mirroring PVA's FieldDesc); the **value
tree** carries data as plain JSON with a few escaping rules driven by the type,
so that the four lossy-JSON hazards are resolved:

* int width <= 32 -> JSON number; int width 64 -> decimal **string**
  (subsumes the "outside +/-2^53" rule: only 64-bit ints can exceed 2^53);
* float NaN/+inf/-inf -> the strings ``"nan"`` / ``"inf"`` / ``"-inf"``;
* ``null`` vs ``[]`` (empty array) vs ``""`` (empty string) stay distinct;
* serialized bytes are NOT part of the normal form (they live in the adapter
  artifact / fixture envelope, recorded as hex).

The JSON Schema in ``schemas/normal-form.schema.json`` validates *shape* only;
the type<->value conformance check lives here in :func:`validate`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Union

SCHEMA_VERSION = "0a"

# --- type-system constants --------------------------------------------------

SCALAR_TYPES = ("int", "float", "string", "boolean")
INT_WIDTHS = (8, 16, 32, 64)
FLOAT_WIDTHS = (32, 64)

# Only 64-bit integers can hold a value whose magnitude exceeds 2**53, so the
# "encode as string" rule reduces to a width test.
_INT_STRING_WIDTH = 64

_FLOAT_TOKENS = {"nan": math.nan, "inf": math.inf, "-inf": -math.inf}


class NormalFormError(ValueError):
    """Raised when a document is structurally invalid or its value tree does
    not conform to its type tree."""


# --- type tree --------------------------------------------------------------

TypeNode = Union["Scalar", "Array", "Struct"]


@dataclass(frozen=True)
class Scalar:
    kind = "scalar"
    type: str
    width: int | None = None
    signed: bool | None = None

    def __post_init__(self) -> None:
        if self.type not in SCALAR_TYPES:
            raise NormalFormError(f"unknown scalar type {self.type!r}")
        if self.type == "int":
            if self.width not in INT_WIDTHS:
                raise NormalFormError(f"int width must be one of {INT_WIDTHS}")
            if not isinstance(self.signed, bool):
                raise NormalFormError("int requires a boolean 'signed'")
        elif self.type == "float":
            if self.width not in FLOAT_WIDTHS:
                raise NormalFormError(f"float width must be one of {FLOAT_WIDTHS}")
            if self.signed is not None:
                raise NormalFormError("float must not carry 'signed'")
        else:  # string / boolean
            if self.width is not None or self.signed is not None:
                raise NormalFormError(f"{self.type} must not carry width/signed")

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"kind": "scalar", "type": self.type}
        if self.width is not None:
            out["width"] = self.width
        if self.signed is not None:
            out["signed"] = self.signed
        return out


@dataclass(frozen=True)
class Array:
    kind = "array"
    element: TypeNode
    bound: int | None = None

    def __post_init__(self) -> None:
        if self.bound is not None and (not isinstance(self.bound, int) or self.bound < 0):
            raise NormalFormError("array bound must be null or a non-negative int")

    def to_json(self) -> dict[str, Any]:
        return {"kind": "array", "element": self.element.to_json(), "bound": self.bound}


@dataclass(frozen=True)
class Field:
    name: str
    type: TypeNode

    def to_json(self) -> dict[str, Any]:
        return {"name": self.name, "type": self.type.to_json()}


@dataclass(frozen=True)
class Struct:
    kind = "struct"
    fields: tuple[Field, ...]
    id: str | None = None

    def __post_init__(self) -> None:
        names = [f.name for f in self.fields]
        if len(names) != len(set(names)):
            raise NormalFormError("struct field names must be unique")

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"kind": "struct"}
        if self.id is not None:
            out["id"] = self.id
        out["fields"] = [f.to_json() for f in self.fields]
        return out


def type_from_json(obj: Any) -> TypeNode:
    """Parse a type-tree JSON object into a :data:`TypeNode`."""
    if not isinstance(obj, dict) or "kind" not in obj:
        raise NormalFormError("type node must be an object with a 'kind'")
    kind = obj["kind"]
    if kind == "scalar":
        return Scalar(type=obj.get("type"), width=obj.get("width"), signed=obj.get("signed"))
    if kind == "array":
        if "element" not in obj:
            raise NormalFormError("array type requires 'element'")
        return Array(element=type_from_json(obj["element"]), bound=obj.get("bound"))
    if kind == "struct":
        fields_json = obj.get("fields")
        if not isinstance(fields_json, list):
            raise NormalFormError("struct type requires a 'fields' list")
        fields = tuple(
            Field(name=f["name"], type=type_from_json(f["type"])) for f in fields_json
        )
        return Struct(fields=fields, id=obj.get("id"))
    raise NormalFormError(f"unsupported type kind {kind!r} (0a supports scalar/array/struct)")


# --- value encoding (native <-> JSON-ready) ---------------------------------


def _int_bounds(width: int, signed: bool) -> tuple[int, int]:
    if signed:
        return -(2 ** (width - 1)), 2 ** (width - 1) - 1
    return 0, 2**width - 1


def encode_int(value: int, width: int, signed: bool) -> int | str:
    """Encode a native int: a JSON number for width <= 32, a decimal string for
    width 64."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise NormalFormError(f"expected int, got {type(value).__name__}")
    lo, hi = _int_bounds(width, signed)
    if not (lo <= value <= hi):
        raise NormalFormError(f"int {value} out of range for {'i' if signed else 'u'}{width}")
    return str(value) if width == _INT_STRING_WIDTH else value


def decode_int(encoded: int | str, width: int, signed: bool) -> int:
    if isinstance(encoded, bool):
        raise NormalFormError("bool is not a valid int encoding")
    if width == _INT_STRING_WIDTH:
        if not isinstance(encoded, str):
            raise NormalFormError("64-bit int must be encoded as a string")
        value = int(encoded)
    else:
        if not isinstance(encoded, int):
            raise NormalFormError(f"int width {width} must be encoded as a JSON number")
        value = encoded
    lo, hi = _int_bounds(width, signed)
    if not (lo <= value <= hi):
        raise NormalFormError(f"decoded int {value} out of range for width {width}")
    return value


def encode_float(value: float) -> float | str:
    """Encode a native float: finite -> JSON number, otherwise an explicit
    token string."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise NormalFormError(f"expected float, got {type(value).__name__}")
    value = float(value)
    if math.isnan(value):
        return "nan"
    if math.isinf(value):
        return "inf" if value > 0 else "-inf"
    return value


def decode_float(encoded: float | int | str) -> float:
    if isinstance(encoded, str):
        if encoded not in _FLOAT_TOKENS:
            raise NormalFormError(f"unknown float token {encoded!r}")
        return _FLOAT_TOKENS[encoded]
    if isinstance(encoded, bool) or not isinstance(encoded, (int, float)):
        raise NormalFormError("float must be a JSON number or token string")
    return float(encoded)


def encode_value(node: TypeNode, native: Any) -> Any:
    """Encode a native value tree into its JSON-ready normal form per ``node``.

    ``None`` is always permitted (a null / absent value, e.g. a missing
    struct-array element)."""
    if native is None:
        return None
    if isinstance(node, Scalar):
        if node.type == "int":
            return encode_int(native, node.width, node.signed)
        if node.type == "float":
            return encode_float(native)
        if node.type == "string":
            if not isinstance(native, str):
                raise NormalFormError(f"expected string, got {type(native).__name__}")
            return native
        if node.type == "boolean":
            if not isinstance(native, bool):
                raise NormalFormError(f"expected bool, got {type(native).__name__}")
            return native
    if isinstance(node, Array):
        if not isinstance(native, (list, tuple)):
            raise NormalFormError(f"expected array, got {type(native).__name__}")
        if node.bound is not None and len(native) > node.bound:
            raise NormalFormError(f"array length {len(native)} exceeds bound {node.bound}")
        return [encode_value(node.element, item) for item in native]
    if isinstance(node, Struct):
        if not isinstance(native, dict):
            raise NormalFormError(f"expected struct mapping, got {type(native).__name__}")
        extra = set(native) - {f.name for f in node.fields}
        if extra:
            raise NormalFormError(f"unexpected struct fields: {sorted(extra)}")
        return {f.name: encode_value(f.type, native.get(f.name)) for f in node.fields}
    raise NormalFormError(f"cannot encode against {node!r}")


def decode_value(node: TypeNode, encoded: Any) -> Any:
    """Inverse of :func:`encode_value`: JSON-ready value tree -> native."""
    if encoded is None:
        return None
    if isinstance(node, Scalar):
        if node.type == "int":
            return decode_int(encoded, node.width, node.signed)
        if node.type == "float":
            return decode_float(encoded)
        if node.type == "string":
            if not isinstance(encoded, str):
                raise NormalFormError("expected JSON string")
            return encoded
        if node.type == "boolean":
            if not isinstance(encoded, bool):
                raise NormalFormError("expected JSON bool")
            return encoded
    if isinstance(node, Array):
        if not isinstance(encoded, list):
            raise NormalFormError("expected JSON array")
        if node.bound is not None and len(encoded) > node.bound:
            raise NormalFormError(f"array length {len(encoded)} exceeds bound {node.bound}")
        return [decode_value(node.element, item) for item in encoded]
    if isinstance(node, Struct):
        if not isinstance(encoded, dict):
            raise NormalFormError("expected JSON object for struct")
        return {f.name: decode_value(f.type, encoded.get(f.name)) for f in node.fields}
    raise NormalFormError(f"cannot decode against {node!r}")


# --- documents --------------------------------------------------------------


def document(node: TypeNode, native: Any) -> dict[str, Any]:
    """Build a complete normal-form document from a type tree and a native
    value tree."""
    return {
        "schema_version": SCHEMA_VERSION,
        "type": node.to_json(),
        "value": encode_value(node, native),
    }


def decode_document(doc: dict[str, Any]) -> tuple[TypeNode, Any]:
    """Parse and validate a document, returning ``(type_node, native_value)``."""
    node = _require_type(doc)
    return node, decode_value(node, doc["value"])


def _require_type(doc: Any) -> TypeNode:
    if not isinstance(doc, dict):
        raise NormalFormError("document must be a JSON object")
    if doc.get("schema_version") != SCHEMA_VERSION:
        raise NormalFormError(f"schema_version must be {SCHEMA_VERSION!r}")
    if "type" not in doc or "value" not in doc:
        raise NormalFormError("document must have 'type' and 'value'")
    return type_from_json(doc["type"])


def validate(doc: dict[str, Any]) -> None:
    """Structural + type<->value conformance check. Raises
    :class:`NormalFormError` on any violation."""
    node = _require_type(doc)
    # Decoding walks the whole value tree against the type and raises on any
    # mismatch, so it doubles as conformance validation.
    decode_value(node, doc["value"])


# --- semantic comparison ----------------------------------------------------


def semantic_equal(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Type-aware equality of two normal-form documents — the primitive behind
    the harness's *semantic match* verdict. Both type trees must match and the
    decoded value trees must be equal (NaN compares equal to NaN; finite floats
    compare by value)."""
    node_a, value_a = decode_document(a)
    node_b, value_b = decode_document(b)
    if node_a.to_json() != node_b.to_json():
        return False
    return _native_equal(value_a, value_b)


def _native_equal(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is b
    if isinstance(a, float) or isinstance(b, float):
        if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
            return False
        if math.isnan(a) and math.isnan(b):
            return True
        return a == b
    if isinstance(a, dict) and isinstance(b, dict):
        if a.keys() != b.keys():
            return False
        return all(_native_equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_native_equal(x, y) for x, y in zip(a, b))
    return type(a) is type(b) and a == b
