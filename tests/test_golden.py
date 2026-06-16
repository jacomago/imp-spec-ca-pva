"""Phase 0b — golden fixtures (oracle v1).

These tests validate everything *around* the hand-verified hex↔decoding link:
shape, type↔value conformance, round-trip idempotence, well-formed hex, and
unique ids. They deliberately do not re-derive a decoding from the bytes — no
decoder exists yet (Phase 2/4) and re-deriving is the whole point of a golden
fixture. See docs/fixtures.md.
"""

import json
from pathlib import Path

import jsonschema
import pytest

from harness import golden, normalform as nf

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"
FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures"

FIXTURES = golden.load_fixtures(FIXTURES_ROOT, validate=False)


def _id(fx: golden.Fixture) -> str:
    return fx.case_id


@pytest.fixture(scope="module")
def normal_form_schema() -> dict:
    return json.loads((SCHEMA_DIR / "normal-form.schema.json").read_text())


def test_fixtures_exist():
    # Guard against an empty glob silently passing every parametrized test.
    assert FIXTURES, "no golden fixtures found under fixtures/"


def test_fixture_schema_is_valid_draft2020():
    schema = json.loads((SCHEMA_DIR / "fixture.schema.json").read_text())
    jsonschema.Draft202012Validator.check_schema(schema)


def test_case_ids_unique():
    ids = [fx.case_id for fx in FIXTURES]
    assert len(ids) == len(set(ids)), "duplicate case_id across fixtures"


@pytest.mark.parametrize("fx", FIXTURES, ids=_id)
def test_fixture_is_shape_valid(fx: golden.Fixture):
    golden.validate_fixture(json.loads(fx.path.read_text()))


@pytest.mark.parametrize("fx", FIXTURES, ids=_id)
def test_segment_hex_is_well_formed(fx: golden.Fixture):
    assert fx.segments, "a fixture must carry at least one segment"
    for name in fx.segments:
        # Raises FixtureError on odd-length / non-hex input.
        fx.segment_bytes(name)


@pytest.mark.parametrize("fx", FIXTURES, ids=_id)
def test_decoded_conforms(fx: golden.Fixture, normal_form_schema: dict):
    doc = fx.normal_form
    if doc is not None:
        # Full normal-form document: shape + type<->value conformance + idempotence.
        jsonschema.Draft202012Validator(normal_form_schema).validate(doc)
        nf.validate(doc)
        node, native = nf.decode_document(doc)
        assert nf.document(node, native) == doc
    elif fx.type_tree is not None:
        # Introspection-only: the type tree must parse and re-serialize stably.
        node = nf.type_from_json(fx.type_tree)
        assert node.to_json() == fx.type_tree
    else:
        # Meta payload (bitset / status): nothing to conform against the normal
        # form; the schema check in test_fixture_is_shape_valid covers it.
        assert fx.meta is not None


def test_timestamp_fixture_is_57_bytes():
    fx = next(f for f in FIXTURES if f.case_id == "pva.introspection.timestamp")
    assert len(fx.segment_bytes("introspection_bytes_hex")) == 57


def test_bitset_decodings_match_bytes():
    # Independent check of the BitSet little-endian bit layout against the hand
    # decoding: byte (i // 8), bit (i % 8).
    for fx in FIXTURES:
        if not (fx.meta and fx.meta["kind"] == "bitset"):
            continue
        raw = fx.segment_bytes("meta_bytes_hex")
        size, body = raw[0], raw[1:]
        assert len(body) == size
        bits = sorted(
            byte_i * 8 + bit
            for byte_i, byte in enumerate(body)
            for bit in range(8)
            if byte & (1 << bit)
        )
        assert bits == fx.meta["indices"], fx.case_id
