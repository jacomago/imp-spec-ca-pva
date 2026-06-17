"""The pure-``ctypes`` CA DBR offline codec — no network, no libca.

``serialize`` packs a native value tree into the DBR struct for its type and
returns the raw big-endian bytes (``RISC_pad`` / string NUL padding left zero).
``deserialize`` casts bytes onto the struct and reads back the value-tree
fields, skipping the pad fields. Both take a normal-form
:class:`~harness.normalform.TypeNode`; the struct layout is selected via the
bijective :mod:`ca.mapping`.
"""

from __future__ import annotations

import ctypes

from harness.normalform import Scalar, Struct, TypeNode

from . import dbr, mapping

_STRING_ENCODING = "utf-8"


def serialize(node: TypeNode, native: object) -> bytes:
    """Pack a native value tree into its DBR struct bytes (big-endian)."""
    code = mapping.code_for_type(node)
    obj = dbr.struct_for_code(code)()
    if dbr.is_base(code):
        _set_scalar(obj, "value", node, native)  # type: ignore[arg-type]
    else:
        _fill_fields(obj, node, native)  # type: ignore[arg-type]
    return bytes(obj)


def deserialize(node: TypeNode, data: bytes) -> object:
    """Read a native value tree from DBR struct bytes for ``node``."""
    code = mapping.code_for_type(node)
    struct_cls = dbr.struct_for_code(code)
    expected = ctypes.sizeof(struct_cls)
    if len(data) != expected:
        raise ValueError(
            f"DBR code {code} expects {expected} bytes, got {len(data)}"
        )
    obj = struct_cls.from_buffer_copy(data)
    if dbr.is_base(code):
        return _get_scalar(obj, "value", node)  # type: ignore[arg-type]
    return _read_fields(obj, node)  # type: ignore[arg-type]


# --- recursive struct <-> value-tree walk -----------------------------------
# The ctypes field names mirror the TypeNode field names exactly; only the
# RISC_pad fields are absent from the TypeNode, so they are never touched (they
# stay zero on serialize and are ignored on deserialize).


def _fill_fields(owner: ctypes.Structure, node: Struct, native: dict) -> None:
    for f in node.fields:
        value = native[f.name]
        if isinstance(f.type, Struct):
            _fill_fields(getattr(owner, f.name), f.type, value)
        else:
            _set_scalar(owner, f.name, f.type, value)


def _read_fields(owner: ctypes.Structure, node: Struct) -> dict:
    out: dict = {}
    for f in node.fields:
        if isinstance(f.type, Struct):
            out[f.name] = _read_fields(getattr(owner, f.name), f.type)
        else:
            out[f.name] = _get_scalar(owner, f.name, f.type)
    return out


def _set_scalar(owner: ctypes.Structure, name: str, node: Scalar, value: object) -> None:
    if node.type == "string":
        if not isinstance(value, str):
            raise TypeError(f"{name}: expected str, got {type(value).__name__}")
        setattr(owner, name, value.encode(_STRING_ENCODING))
    else:
        setattr(owner, name, value)


def _get_scalar(owner: ctypes.Structure, name: str, node: Scalar) -> object:
    raw = getattr(owner, name)
    if node.type == "string":
        # A c_char array reads back as bytes already trimmed at the first NUL.
        return raw.decode(_STRING_ENCODING)
    if node.type == "float":
        return float(raw)
    return int(raw)
