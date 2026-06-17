"""``ctypes`` mirrors of the CA DBR struct layouts.

libca exposes no offline codec, so the adapter re-implements EPICS base's
``dbr.h`` struct layouts directly (``epics-base`` ``modules/ca/src/client/
db_access.h``). Every struct is a :class:`ctypes.BigEndianStructure` (CA is
network byte order) with ``_pack_ = 1`` so the layout is exactly the field list
below — including the explicit ``RISC_pad`` alignment bytes that several DBR
structs carry. Those pad fields are wire-only (a byte-identical degree of
freedom); they are never part of the normal-form value tree.

There are 21 DBR codes: seven base types (0–6) and their ``DBR_STS_*`` (7–13)
and ``DBR_TIME_*`` (14–20) metadata variants. The byte sizes here match
``CA_DBR_BYTE_SIZES`` in ``tests/test_golden.py``.
"""

from __future__ import annotations

import ctypes

# --- DBR code constants -----------------------------------------------------

DBR_STRING = 0
DBR_SHORT = 1  # alias DBR_INT
DBR_FLOAT = 2
DBR_ENUM = 3
DBR_CHAR = 4
DBR_LONG = 5
DBR_DOUBLE = 6

# Base codes, in code order. STS_* = base + 7, TIME_* = base + 14.
BASE_CODES = (DBR_STRING, DBR_SHORT, DBR_FLOAT, DBR_ENUM, DBR_CHAR, DBR_LONG, DBR_DOUBLE)
STS_OFFSET = 7
TIME_OFFSET = 14

MAX_STRING_SIZE = 40  # epicsOldString = char[40]

# Short names per base code, for readable generated struct/class names.
_BASE_NAME = {
    DBR_STRING: "string",
    DBR_SHORT: "short",
    DBR_FLOAT: "float",
    DBR_ENUM: "enum",
    DBR_CHAR: "char",
    DBR_LONG: "long",
    DBR_DOUBLE: "double",
}

# The C value type for each base DBR code (the trailing ``value`` field).
_BASE_CTYPE = {
    DBR_STRING: ctypes.c_char * MAX_STRING_SIZE,  # epicsOldString
    DBR_SHORT: ctypes.c_int16,                    # epicsInt16
    DBR_FLOAT: ctypes.c_float,                    # epicsFloat32
    DBR_ENUM: ctypes.c_uint16,                    # epicsUInt16
    DBR_CHAR: ctypes.c_uint8,                     # epicsUInt8
    DBR_LONG: ctypes.c_int32,                     # epicsInt32
    DBR_DOUBLE: ctypes.c_double,                  # epicsFloat64
}

# RISC_pad alignment bytes that align ``value`` to its natural boundary. Keyed
# by base code; absent means no padding for that variant.
_STS_PAD = {
    DBR_CHAR: [("RISC_pad", ctypes.c_uint8)],   # 1 byte before the u8 value
    DBR_DOUBLE: [("RISC_pad", ctypes.c_int32)],  # 4 bytes before the f64 value
}
_TIME_PAD = {
    DBR_SHORT: [("RISC_pad", ctypes.c_int16)],   # 2 bytes
    DBR_ENUM: [("RISC_pad", ctypes.c_int16)],    # 2 bytes
    DBR_CHAR: [("RISC_pad0", ctypes.c_int16), ("RISC_pad1", ctypes.c_uint8)],  # 2 + 1
    DBR_DOUBLE: [("RISC_pad", ctypes.c_int32)],  # 4 bytes
}


def _struct(name: str, fields: list[tuple[str, type]]) -> type[ctypes.BigEndianStructure]:
    return type(name, (ctypes.BigEndianStructure,), {"_pack_": 1, "_fields_": fields})


# epicsTimeStamp { uint32 secPastEpoch; uint32 nsec; } — counts from the EPICS
# epoch (1990-01-01). Shared by every DBR_TIME_* struct.
DbrTimeStamp = _struct(
    "DbrTimeStamp",
    [("secPastEpoch", ctypes.c_uint32), ("nsec", ctypes.c_uint32)],
)

_STATUS_FIELDS = [("status", ctypes.c_int16), ("severity", ctypes.c_int16)]

# code -> BigEndianStructure subclass mirroring that DBR layout.
STRUCT_BY_CODE: dict[int, type[ctypes.BigEndianStructure]] = {}
for _base in BASE_CODES:
    _name = _BASE_NAME[_base]
    _value = ("value", _BASE_CTYPE[_base])

    STRUCT_BY_CODE[_base] = _struct(f"DbrBase_{_name}", [_value])
    STRUCT_BY_CODE[_base + STS_OFFSET] = _struct(
        f"DbrSts_{_name}", _STATUS_FIELDS + _STS_PAD.get(_base, []) + [_value]
    )
    STRUCT_BY_CODE[_base + TIME_OFFSET] = _struct(
        f"DbrTime_{_name}",
        _STATUS_FIELDS
        + [("stamp", DbrTimeStamp)]
        + _TIME_PAD.get(_base, [])
        + [_value],
    )

ALL_CODES = tuple(sorted(STRUCT_BY_CODE))


def is_base(code: int) -> bool:
    """True for the seven plain base DBR codes (0–6), which wrap a bare scalar
    in a single ``value`` field rather than a status/time struct."""
    return code in BASE_CODES


def struct_for_code(code: int) -> type[ctypes.BigEndianStructure]:
    try:
        return STRUCT_BY_CODE[code]
    except KeyError:
        raise ValueError(f"unknown DBR code {code}") from None
