"""Tests for the CA DBR offline codec adapter (Phase 0c-2).

Pure Python — no EPICS installed. The adapter is driven through the real
``harness.io.run_adapter`` loop (which validates every request and response
against ``schemas/adapter-io.schema.json``) and adjudicated against the 21
hand-authored CA golden fixtures from 0c-1.
"""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import pytest

import ca
from ca import codec, dbr, mapping
from harness import golden, io
from harness import normalform as nf

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_ROOT = REPO_ROOT / "fixtures" / "ca"
SEED_CORPUS = REPO_ROOT / "adapters" / "ca" / "corpus" / "seed.jsonl"

CA_FIXTURES = [f for f in golden.load_fixtures(FIXTURES_ROOT, validate=False) if f.protocol == "ca"]


def _id(fx: golden.Fixture) -> str:
    return fx.case_id


def _run(requests: list[io.Request]) -> list[dict]:
    """Drive the adapter over an in-memory JSON Lines stream, as a corpus run
    would, and return the parsed response objects (response schema enforced)."""
    in_stream = StringIO("\n".join(json.dumps(r.to_json()) for r in requests) + "\n")
    out_stream = StringIO()
    io.run_adapter(ca.ADAPTER, ca.handler, in_stream, out_stream)
    return [json.loads(line) for line in out_stream.getvalue().splitlines()]


# --- adjudication against the golden fixtures --------------------------------


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


@pytest.mark.parametrize("fx", CA_FIXTURES, ids=_id)
def test_round_trip(fx: golden.Fixture):
    doc = fx.normal_form
    node = nf.type_from_json(doc["type"])
    native = nf.decode_value(node, doc["value"])
    raw = golden.canonical_hex(fx.segments["value_bytes_hex"])

    # value -> bytes -> value is loss-free (semantic).
    assert nf.encode_value(node, codec.deserialize(node, codec.serialize(node, native))) == doc["value"]
    # bytes -> value -> bytes is byte-identical (incl. RISC_pad / NUL padding).
    assert codec.serialize(node, codec.deserialize(node, bytes.fromhex(raw))).hex() == raw


# --- the bijective mapping covers the full DBR matrix ------------------------


def test_mapping_is_a_bijection_over_all_codes():
    assert len(dbr.ALL_CODES) == 21
    for code in dbr.ALL_CODES:
        assert mapping.code_for_type(mapping.type_for_code(code)) == code
    # distinct TypeNode per code (no two codes collapse to the same type).
    assert len({mapping.type_for_code(c) for c in dbr.ALL_CODES}) == 21


def test_fixtures_cover_every_dbr_code():
    fixture_codes = {mapping.code_for_type(nf.type_from_json(fx.normal_form["type"])) for fx in CA_FIXTURES}
    assert fixture_codes == set(dbr.ALL_CODES)


# --- the seed corpus deliverable --------------------------------------------


def _seed_requests() -> list[dict]:
    return [json.loads(line) for line in SEED_CORPUS.read_text().splitlines() if line.strip()]


def test_seed_corpus_is_schema_valid():
    objs = _seed_requests()
    assert len(objs) == 2 * len(CA_FIXTURES)  # one serialize + one deserialize each
    for obj in objs:
        io.validate_request(obj)


def test_seed_corpus_runs_clean():
    requests = [io.Request.from_json(obj) for obj in _seed_requests()]
    responses = _run(requests)
    assert len(responses) == len(requests)
    assert all(r["status"] == "ok" for r in responses)


# --- provenance is lazy (no pyepics in pure-Python CI) -----------------------


def test_provenance_records_pyepics_without_importing_it():
    extra = ca.ADAPTER.extra
    assert extra is not None
    assert extra["codec"] == "pure-ctypes"
    # pyepics is absent in pure-Python CI -> recorded as None, never raised.
    assert "pyepics" in extra


def test_deserialize_without_type_is_a_clean_error():
    req = io.Request(operation="deserialize", case_id="no-type", bytes_hex="0041", type=None)
    (resp,) = _run([req])
    assert resp["status"] == "error"
    assert resp["error"]["kind"] == "ValueError"
