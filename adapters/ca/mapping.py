"""The bijective DBR-code <-> normal-form ``TypeNode`` mapping.

Pinned in ``docs/normal-form.md`` and anchored by ``fixtures/ca/``. CA carries
no self-describing type information, so the DBR code *is* the type; each of the
21 codes maps to one distinct top-level :class:`~harness.normalform.TypeNode`,
making the map a bijection. ``status``/``severity``/``stamp`` are first-class
value-tree fields; ``RISC_pad`` and string NUL padding (handled in
:mod:`ca.dbr`) are not.
"""

from __future__ import annotations

from harness.normalform import Field, Scalar, Struct, TypeNode

from . import dbr

_I16 = Scalar("int", 16, True)
_U16 = Scalar("int", 16, False)
_U32 = Scalar("int", 32, False)

# Base DBR code -> the scalar it decodes to (DBR_ENUM is the raw uint16 index).
_BASE_SCALAR: dict[int, Scalar] = {
    dbr.DBR_STRING: Scalar("string"),
    dbr.DBR_SHORT: _I16,
    dbr.DBR_FLOAT: Scalar("float", 32),
    dbr.DBR_ENUM: _U16,
    dbr.DBR_CHAR: Scalar("int", 8, False),
    dbr.DBR_LONG: Scalar("int", 32, True),
    dbr.DBR_DOUBLE: Scalar("float", 64),
}

_STAMP = Struct(fields=(Field("secPastEpoch", _U32), Field("nsec", _U32)))


def _sts(value: TypeNode) -> Struct:
    return Struct(
        fields=(Field("status", _I16), Field("severity", _I16), Field("value", value))
    )


def _time(value: TypeNode) -> Struct:
    return Struct(
        fields=(
            Field("status", _I16),
            Field("severity", _I16),
            Field("stamp", _STAMP),
            Field("value", value),
        )
    )


# code -> TypeNode (the forward map).
TYPE_BY_CODE: dict[int, TypeNode] = {}
for _base, _scalar in _BASE_SCALAR.items():
    TYPE_BY_CODE[_base] = _scalar
    TYPE_BY_CODE[_base + dbr.STS_OFFSET] = _sts(_scalar)
    TYPE_BY_CODE[_base + dbr.TIME_OFFSET] = _time(_scalar)

# TypeNode -> code (the inverse). Frozen dataclasses are hashable, and
# ``type_from_json`` rebuilds equal nodes, so request types look up directly.
_CODE_BY_TYPE: dict[TypeNode, int] = {node: code for code, node in TYPE_BY_CODE.items()}


def type_for_code(code: int) -> TypeNode:
    try:
        return TYPE_BY_CODE[code]
    except KeyError:
        raise ValueError(f"unknown DBR code {code}") from None


def code_for_type(node: TypeNode) -> int:
    try:
        return _CODE_BY_TYPE[node]
    except KeyError:
        raise ValueError(f"type does not map to any CA DBR code: {node!r}") from None
