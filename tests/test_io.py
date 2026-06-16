import io as _io

from harness import io, normalform as nf
from harness.io import AdapterInfo, Request, Response


ADAPTER = AdapterInfo(name="echo", version="0.0.0", extra={"note": "test"})


def test_request_round_trip_serialize():
    t = nf.Scalar("int", 64, False).to_json()
    req = Request(operation="serialize", case_id="c1", type=t, value="42")
    parsed = Request.from_json(req.to_json())
    assert parsed == req


def test_request_round_trip_deserialize():
    req = Request(operation="deserialize", case_id="c2", bytes_hex="00ff", type=None)
    parsed = Request.from_json(req.to_json())
    assert parsed.operation == "deserialize"
    assert parsed.bytes_hex == "00ff"


def test_response_round_trip():
    resp = Response(
        case_id="c1",
        operation="serialize",
        adapter=ADAPTER,
        status="ok",
        result=io.serialize_result("00ff"),
    )
    parsed = Response.from_json(resp.to_json())
    assert parsed == resp


def _handler(request: Request) -> Response:
    if request.operation == "serialize":
        return Response(
            case_id=request.case_id,
            operation="serialize",
            adapter=ADAPTER,
            result=io.serialize_result("deadbeef"),
        )
    return Response(
        case_id=request.case_id,
        operation="deserialize",
        adapter=ADAPTER,
        result=io.deserialize_result(
            nf.Scalar("int", 32, True).to_json(), nf.decode_value(nf.Scalar("int", 32, True), 7)
        ),
    )


def test_run_adapter_streams_jsonl():
    t = nf.Scalar("int", 32, True).to_json()
    lines = [
        Request(operation="serialize", case_id="a", type=t, value=7).to_json(),
        Request(operation="deserialize", case_id="b", bytes_hex="07000000").to_json(),
    ]
    import json

    in_stream = _io.StringIO("\n".join(json.dumps(x) for x in lines) + "\n")
    out_stream = _io.StringIO()
    io.run_adapter(ADAPTER, _handler, in_stream, out_stream)

    out_lines = [json.loads(x) for x in out_stream.getvalue().splitlines()]
    assert len(out_lines) == 2
    assert out_lines[0]["status"] == "ok"
    assert out_lines[0]["result"]["bytes_hex"] == "deadbeef"
    assert out_lines[1]["result"]["value"] == 7


def test_run_adapter_captures_handler_error():
    def boom(_request: Request) -> Response:
        raise ValueError("nope")

    import json

    req = Request(operation="serialize", case_id="x", type=nf.Scalar("boolean").to_json(), value=True)
    in_stream = _io.StringIO(json.dumps(req.to_json()) + "\n")
    out_stream = _io.StringIO()
    io.run_adapter(ADAPTER, boom, in_stream, out_stream)

    out = json.loads(out_stream.getvalue())
    assert out["status"] == "error"
    assert out["error"]["kind"] == "ValueError"
    assert out["error"]["message"] == "nope"
