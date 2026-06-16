import math

import pytest

from harness import normalform as nf
from harness.normalform import Array, Field, NormalFormError, Scalar, Struct


# --- scalar round-trips -----------------------------------------------------


def test_int32_is_number_int64_is_string():
    i32 = Scalar("int", 32, True)
    i64 = Scalar("int", 64, True)
    assert nf.encode_value(i32, 42) == 42
    assert nf.encode_value(i64, 42) == "42"
    assert nf.decode_value(i32, 42) == 42
    assert nf.decode_value(i64, "42") == 42


def test_uint32_max_is_number_uint64_max_is_string():
    u32 = Scalar("int", 32, False)
    u64 = Scalar("int", 64, False)
    assert nf.encode_value(u32, 2**32 - 1) == 2**32 - 1
    assert nf.encode_value(u64, 2**64 - 1) == "18446744073709551615"
    assert nf.decode_value(u64, "18446744073709551615") == 2**64 - 1


def test_int_range_is_enforced():
    with pytest.raises(NormalFormError):
        nf.encode_value(Scalar("int", 8, True), 200)
    with pytest.raises(NormalFormError):
        nf.encode_value(Scalar("int", 8, False), -1)


def test_int64_must_be_string_on_decode():
    with pytest.raises(NormalFormError):
        nf.decode_value(Scalar("int", 64, True), 42)


@pytest.mark.parametrize(
    "native, encoded",
    [(math.nan, "nan"), (math.inf, "inf"), (-math.inf, "-inf"), (1.5, 1.5)],
)
def test_float_non_finite_tokens(native, encoded):
    f64 = Scalar("float", 64)
    out = nf.encode_value(f64, native)
    assert out == encoded
    decoded = nf.decode_value(f64, out)
    if isinstance(native, float) and math.isnan(native):
        assert math.isnan(decoded)
    else:
        assert decoded == native


def test_string_and_boolean():
    assert nf.encode_value(Scalar("string"), "hi") == "hi"
    assert nf.encode_value(Scalar("boolean"), True) is True
    with pytest.raises(NormalFormError):
        nf.encode_value(Scalar("boolean"), 1)  # int is not a bool


# --- null / empty distinctions ----------------------------------------------


def test_null_empty_array_empty_string_are_distinct():
    arr = Array(Scalar("int", 32, True))
    assert nf.encode_value(arr, []) == []
    assert nf.encode_value(arr, None) is None
    assert nf.encode_value(Scalar("string"), "") == ""
    assert nf.encode_value(Scalar("string"), None) is None


def test_array_bound_enforced():
    bounded = Array(Scalar("int", 8, True), bound=2)
    with pytest.raises(NormalFormError):
        nf.encode_value(bounded, [1, 2, 3])


# --- composite round-trip ---------------------------------------------------


def _timestamp_type() -> Struct:
    return Struct(
        id="timeStamp_t",
        fields=(
            Field("secondsPastEpoch", Scalar("int", 64, True)),
            Field("nanoseconds", Scalar("int", 32, False)),
            Field("userTag", Scalar("int", 32, True)),
        ),
    )


def test_document_round_trip():
    t = _timestamp_type()
    native = {"secondsPastEpoch": 1600000000, "nanoseconds": 123456789, "userTag": 0}
    doc = nf.document(t, native)
    assert doc["value"]["secondsPastEpoch"] == "1600000000"
    assert doc["value"]["nanoseconds"] == 123456789
    nf.validate(doc)
    node, decoded = nf.decode_document(doc)
    assert node.to_json() == t.to_json()
    assert decoded == native


def test_validate_rejects_type_value_mismatch():
    t = _timestamp_type()
    doc = nf.document(t, {"secondsPastEpoch": 1, "nanoseconds": 2, "userTag": 3})
    doc["value"]["secondsPastEpoch"] = 1  # width-64 must be a string, not a number
    with pytest.raises(NormalFormError):
        nf.validate(doc)


def test_unknown_kind_rejected():
    with pytest.raises(NormalFormError):
        nf.type_from_json({"kind": "enum"})


def test_struct_duplicate_field_names_rejected():
    with pytest.raises(NormalFormError):
        Struct(fields=(Field("a", Scalar("boolean")), Field("a", Scalar("boolean"))))


# --- semantic equality ------------------------------------------------------


def test_semantic_equal_nan_matches_nan():
    f = Scalar("float", 64)
    a = nf.document(f, math.nan)
    b = nf.document(f, math.nan)
    assert nf.semantic_equal(a, b)


def test_semantic_equal_distinguishes_values_and_types():
    i32 = Scalar("int", 32, True)
    assert not nf.semantic_equal(nf.document(i32, 1), nf.document(i32, 2))
    # same value, different type tree -> not a semantic match
    assert not nf.semantic_equal(
        nf.document(Scalar("int", 32, True), 1), nf.document(Scalar("int", 64, True), 1)
    )


def test_semantic_equal_null_vs_empty():
    arr = Array(Scalar("int", 8, True))
    assert not nf.semantic_equal(nf.document(arr, None), nf.document(arr, []))
