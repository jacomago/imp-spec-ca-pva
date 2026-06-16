import json
from pathlib import Path

import jsonschema
import pytest

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"


def _load(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text())


@pytest.fixture(scope="module")
def normal_form_schema() -> dict:
    return _load("normal-form.schema.json")


@pytest.fixture(scope="module")
def adapter_io_schema() -> dict:
    return _load("adapter-io.schema.json")


@pytest.fixture(scope="module")
def fixture_schema() -> dict:
    return _load("fixture.schema.json")


def test_schemas_are_valid_draft2020(normal_form_schema, adapter_io_schema, fixture_schema):
    jsonschema.Draft202012Validator.check_schema(normal_form_schema)
    jsonschema.Draft202012Validator.check_schema(adapter_io_schema)
    jsonschema.Draft202012Validator.check_schema(fixture_schema)


# --- normal form ------------------------------------------------------------

VALID_DOCS = [
    {
        "schema_version": "0a",
        "type": {"kind": "scalar", "type": "int", "width": 64, "signed": False},
        "value": "18446744073709551615",
    },
    {
        "schema_version": "0a",
        "type": {"kind": "scalar", "type": "float", "width": 32},
        "value": "nan",
    },
    {
        "schema_version": "0a",
        "type": {
            "kind": "struct",
            "id": "timeStamp_t",
            "fields": [
                {"name": "secondsPastEpoch", "type": {"kind": "scalar", "type": "int", "width": 64, "signed": True}},
                {"name": "nanoseconds", "type": {"kind": "scalar", "type": "int", "width": 32, "signed": False}},
            ],
        },
        "value": {"secondsPastEpoch": "1600000000", "nanoseconds": 123456789},
    },
    {
        "schema_version": "0a",
        "type": {"kind": "array", "element": {"kind": "scalar", "type": "boolean"}, "bound": None},
        "value": [],
    },
]

INVALID_DOCS = [
    # int scalar missing required width/signed
    {"schema_version": "0a", "type": {"kind": "scalar", "type": "int"}, "value": 1},
    # float must not carry signed
    {"schema_version": "0a", "type": {"kind": "scalar", "type": "float", "width": 64, "signed": True}, "value": 1.0},
    # bad int width
    {"schema_version": "0a", "type": {"kind": "scalar", "type": "int", "width": 24, "signed": True}, "value": 1},
    # wrong schema version
    {"schema_version": "1", "type": {"kind": "scalar", "type": "boolean"}, "value": True},
    # unknown kind
    {"schema_version": "0a", "type": {"kind": "enum"}, "value": 0},
]


@pytest.mark.parametrize("doc", VALID_DOCS)
def test_valid_normal_form_docs(normal_form_schema, doc):
    jsonschema.Draft202012Validator(normal_form_schema).validate(doc)


@pytest.mark.parametrize("doc", INVALID_DOCS)
def test_invalid_normal_form_docs(normal_form_schema, doc):
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(normal_form_schema).validate(doc)


# --- adapter I/O ------------------------------------------------------------

VALID_REQUESTS = [
    {
        "schema_version": "0a",
        "operation": "serialize",
        "case_id": "c1",
        "type": {"kind": "scalar", "type": "int", "width": 32, "signed": True},
        "value": 7,
    },
    {"schema_version": "0a", "operation": "deserialize", "case_id": "c2", "bytes_hex": "00ff", "type": None},
]

INVALID_REQUESTS = [
    # serialize missing value
    {"schema_version": "0a", "operation": "serialize", "case_id": "c1", "type": {}},
    # deserialize with odd-length hex
    {"schema_version": "0a", "operation": "deserialize", "case_id": "c2", "bytes_hex": "0f0"},
    # unknown operation
    {"schema_version": "0a", "operation": "transcode", "case_id": "c3"},
]

VALID_RESPONSES = [
    {
        "schema_version": "0a",
        "case_id": "c1",
        "operation": "serialize",
        "adapter": {"name": "echo", "version": "0.0.0"},
        "status": "ok",
        "result": {"bytes_hex": "deadbeef"},
    },
    {
        "schema_version": "0a",
        "case_id": "c2",
        "operation": "deserialize",
        "adapter": {"name": "echo", "version": "0.0.0"},
        "status": "error",
        "error": {"kind": "ValueError", "message": "nope"},
    },
]

INVALID_RESPONSES = [
    # ok status without result
    {
        "schema_version": "0a",
        "case_id": "c1",
        "operation": "serialize",
        "adapter": {"name": "echo", "version": "0.0.0"},
        "status": "ok",
    },
    # error status without error
    {
        "schema_version": "0a",
        "case_id": "c1",
        "operation": "serialize",
        "adapter": {"name": "echo", "version": "0.0.0"},
        "status": "error",
    },
]


@pytest.mark.parametrize("req", VALID_REQUESTS)
def test_valid_requests(adapter_io_schema, req):
    jsonschema.Draft202012Validator(adapter_io_schema).validate({"request": req})


@pytest.mark.parametrize("req", INVALID_REQUESTS)
def test_invalid_requests(adapter_io_schema, req):
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(adapter_io_schema).validate({"request": req})


@pytest.mark.parametrize("resp", VALID_RESPONSES)
def test_valid_responses(adapter_io_schema, resp):
    jsonschema.Draft202012Validator(adapter_io_schema).validate({"response": resp})


@pytest.mark.parametrize("resp", INVALID_RESPONSES)
def test_invalid_responses(adapter_io_schema, resp):
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(adapter_io_schema).validate({"response": resp})


# --- golden fixtures --------------------------------------------------------


def _fixture(decoded, **over):
    base = {
        "case_id": "pva.test.case",
        "protocol": "pva",
        "byte_order": "little",
        "source": {"spec": "s", "url": "https://example.org", "section": "x"},
        "segments": {"meta_bytes_hex": "00"},
        "decoded": decoded,
    }
    base.update(over)
    return base


VALID_FIXTURES = [
    # introspection-only: type tree, no value
    _fixture({"type": {"kind": "scalar", "type": "boolean"}}),
    # full normal-form document
    _fixture(
        {"schema_version": "0a", "type": {"kind": "scalar", "type": "int", "width": 32, "signed": True}, "value": 7},
        segments={"value_bytes_hex": "07000000"},
    ),
    # meta: bitset
    _fixture({"meta": {"kind": "bitset", "indices": [0, 1, 2, 4]}}, segments={"meta_bytes_hex": "01 17"}),
    # meta: status
    _fixture({"meta": {"kind": "status", "type": "OK", "message": "", "call_tree": ""}}, segments={"meta_bytes_hex": "FF"}),
]

INVALID_FIXTURES = [
    # decoded matches no branch (document missing schema_version but has value)
    _fixture({"type": {"kind": "scalar", "type": "boolean"}, "value": True}),
    # bitset meta missing required indices
    _fixture({"meta": {"kind": "bitset"}}),
    # status meta missing required message/call_tree
    _fixture({"meta": {"kind": "status", "type": "OK"}}),
    # no segments
    _fixture({"type": {"kind": "scalar", "type": "boolean"}}, segments={}),
    # bad case_id (uppercase / no dot)
    _fixture({"type": {"kind": "scalar", "type": "boolean"}}, case_id="Bad"),
    # unknown protocol
    _fixture({"type": {"kind": "scalar", "type": "boolean"}}, protocol="http"),
]


@pytest.mark.parametrize("fx", VALID_FIXTURES)
def test_valid_fixtures(fixture_schema, fx):
    jsonschema.Draft202012Validator(fixture_schema).validate(fx)


@pytest.mark.parametrize("fx", INVALID_FIXTURES)
def test_invalid_fixtures(fixture_schema, fx):
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(fixture_schema).validate(fx)
