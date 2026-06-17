"""CA DBR offline codec adapter (Phase 0c-2).

The first concrete adapter for the harness's adapter contract. Pure-``ctypes``
mirrors of EPICS base ``db_access.h`` DBR layouts, a bijective DBR-code <->
normal-form ``TypeNode`` mapping, and a ``serialize``/``deserialize`` codec
driven by ``harness.io.run_adapter``. No network, no libca.
"""

from __future__ import annotations

from .adapter import ADAPTER, handler, main
from .codec import deserialize, serialize
from .mapping import code_for_type, type_for_code

__all__ = [
    "ADAPTER",
    "handler",
    "main",
    "serialize",
    "deserialize",
    "code_for_type",
    "type_for_code",
]
