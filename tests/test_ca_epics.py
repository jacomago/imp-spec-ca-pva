"""Real-EPICS cross-checks for the CA DBR adapter (Phase 0c-3).

These tests verify the adapter's hand-authored ``ctypes`` layouts against an
*actual* EPICS library, fulfilling the "machine-verified against real EPICS in
0c-3" promise carried by every ``fixtures/ca/*.json`` ``source.note``.

They only run where pyepics/libca is installed — i.e. inside the conda-forge
adapter container (``adapters/ca/Dockerfile``). In the repo's pure-Python CI
pyepics is absent, so the module is **skipped**, not failed:

    docker run --rm --entrypoint pytest <image> -q

The cross-check is fully offline: it reads libca's own ``dbr_size`` table and
re-checks the static golden fixtures. No CA connection is made.
"""

from __future__ import annotations

import ctypes
import json
from io import StringIO
from pathlib import Path

import pytest

epics = pytest.importorskip("epics")  # no pyepics in pure-Python CI -> skip module

import ca  # noqa: E402  (import after the skip guard, by design)
from ca import dbr  # noqa: E402
from harness import golden, io  # noqa: E402
from harness import normalform as nf  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_ROOT = REPO_ROOT / "fixtures" / "ca"

CA_FIXTURES = [f for f in golden.load_fixtures(FIXTURES_ROOT, validate=False) if f.protocol == "ca"]


def _id(fx: golden.Fixture) -> str:
    return fx.case_id


def _run(requests: list[io.Request]) -> list[dict]:
    """Drive the adapter over an in-memory JSON Lines stream (as a corpus run
    would) and return the parsed, schema-validated responses."""
    in_stream = StringIO("\n".join(json.dumps(r.to_json()) for r in requests) + "\n")
    out_stream = StringIO()
    io.run_adapter(ca.ADAPTER, ca.handler, in_stream, out_stream)
    return [json.loads(line) for line in out_stream.getvalue().splitlines()]


# --- the real-EPICS layout cross-check (the new 0c-3 verification) -----------


def _libca_dbr_size_table() -> ctypes.Array:
    """libca's own ``dbr_size[]``: the byte size of the DBR struct that holds a
    single value of each type, taken straight from the loaded library as the
    real-EPICS source of truth. Element type is ``const unsigned short`` per
    EPICS base ``db_access.h`` / ``db_access.c``."""
    libca = epics.ca.initialize_libca()
    n = max(dbr.ALL_CODES) + 1
    return (ctypes.c_ushort * n).in_dll(libca, "dbr_size")


@pytest.mark.parametrize("code", dbr.ALL_CODES)
def test_ctypes_layout_matches_libca_dbr_size(code: int):
    """Our hand-authored ``ctypes`` mirror is byte-for-byte the size libca
    itself reports for that DBR struct — including the explicit RISC_pad bytes."""
    table = _libca_dbr_size_table()
    assert ctypes.sizeof(dbr.struct_for_code(code)) == table[code]


# --- the golden fixtures, re-adjudicated inside the real-EPICS image ----------


@pytest.mark.parametrize("fx", CA_FIXTURES, ids=_id)
def test_serialize_matches_golden_bytes(fx: golden.Fixture):
    doc = fx.normal_form
    req = io.Request(operation="serialize", case_id=fx.case_id, type=doc["type"], value=doc["value"])
    (resp,) = _run([req])
    assert resp["status"] == "ok"
    assert resp["result"]["bytes_hex"] == golden.canonical_hex(fx.segments["value_bytes_hex"])


@pytest.mark.parametrize("fx", CA_FIXTURES, ids=_id)
def test_deserialize_matches_golden_value(fx: golden.Fixture):
    doc = fx.normal_form
    req = io.Request(
        operation="deserialize",
        case_id=fx.case_id,
        bytes_hex=golden.canonical_hex(fx.segments["value_bytes_hex"]),
        type=doc["type"],
    )
    (resp,) = _run([req])
    assert resp["status"] == "ok"
    got = {"schema_version": "0a", "type": resp["result"]["type"], "value": resp["result"]["value"]}
    assert nf.semantic_equal(got, doc)


# --- provenance is now pinned to the container's real packages ----------------


def test_provenance_pins_real_versions():
    """In the container pyepics and libca are present, so ``extra`` carries
    concrete version strings rather than the ``null`` of pure-Python CI."""
    extra = ca.ADAPTER.extra
    assert extra is not None
    assert extra["codec"] == "pure-ctypes"
    assert extra["pyepics"], "pyepics version should be pinned in the container"
    assert extra["libca"], "libca (ca_version) should be reported in the container"
    assert extra["epics_base"], "epics-base version should be pinned in the container"
