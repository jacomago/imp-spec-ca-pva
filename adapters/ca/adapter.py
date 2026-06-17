"""The CA DBR adapter: the first concrete participant in the adapter contract.

Wires the pure-``ctypes`` :mod:`ca.codec` to the harness I/O loop
(:func:`harness.io.run_adapter`). The codec needs no EPICS at all; pyepics is an
*optional* dependency read only for the provenance record (``AdapterInfo.extra``)
— in pure-Python CI it is absent and recorded as ``null``. The real version pin
is captured when this runs in its conda-forge container (Phase 0c-3).
"""

from __future__ import annotations

import ctypes
from typing import Any

from harness import io
from harness.normalform import type_from_json

from . import codec

ADAPTER_NAME = "ca-dbr"
ADAPTER_VERSION = "0.0.0"


def _epics_base_version() -> str | None:
    """Best-effort EPICS base / libca version string, read via pyepics. Returns
    ``None`` when libca is unavailable (e.g. pure-Python CI). Loading libca is
    offline (no CA connection is made), and any failure degrades to ``None``."""
    try:
        from epics import ca  # type: ignore

        libca = ca.initialize_libca()
        libca.ca_version.restype = ctypes.c_char_p
        return libca.ca_version().decode()
    except Exception:  # noqa: BLE001 - any failure means "unavailable"
        return None


def _provenance() -> dict[str, Any]:
    """Best-effort EPICS provenance. pyepics (and libca) are not installed in
    the pure-Python harness, so a missing import is expected and recorded as
    ``None`` rather than raised. The conda-forge container (0c-3) supplies the
    real pins — ``pyepics`` and ``epics_base`` then carry concrete versions."""
    extra: dict[str, Any] = {"codec": "pure-ctypes"}
    try:
        import epics  # type: ignore
    except Exception:  # noqa: BLE001 - any import failure means "unavailable"
        extra["pyepics"] = None
    else:
        extra["pyepics"] = getattr(epics, "__version__", None)
    extra["epics_base"] = _epics_base_version()
    return extra


ADAPTER = io.AdapterInfo(name=ADAPTER_NAME, version=ADAPTER_VERSION, extra=_provenance())


def handler(request: io.Request) -> io.Response:
    """Map a serialize/deserialize :class:`~harness.io.Request` to a Response.

    CA bytes are not self-describing, so a ``deserialize`` request must carry the
    ``type`` (the DBR layout to read). Exceptions propagate to ``run_adapter``,
    which records them as an ``error`` response."""
    if request.operation == "serialize":
        node = type_from_json(request.type)
        native = io.decode_value(node, request.value)
        data = codec.serialize(node, native)
        result = io.serialize_result(data.hex())
    else:  # deserialize
        if request.type is None:
            raise ValueError("CA deserialize requires a 'type' (DBR bytes are untyped)")
        node = type_from_json(request.type)
        native = codec.deserialize(node, bytes.fromhex(request.bytes_hex or ""))
        result = io.deserialize_result(node.to_json(), io.encode_value(node, native))
    return io.Response(
        case_id=request.case_id,
        operation=request.operation,
        adapter=ADAPTER,
        result=result,
    )


def main() -> None:
    io.run_adapter(ADAPTER, handler)


if __name__ == "__main__":
    main()
