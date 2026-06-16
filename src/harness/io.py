"""The adapter I/O contract (contract #1's wire form).

Every participant is an *adapter* that exposes::

    serialize(value_spec)          -> bytes
    deserialize(bytes, fielddesc?) -> value_tree

offline, with no network. Adapters run in their own container and communicate
over stdin/stdout. The wire format is **JSON Lines**: one request object per
input line, one response (artifact) object per output line, so a whole corpus
streams through without buffering.

Envelopes are validated against ``schemas/adapter-io.schema.json``. The
``result`` value trees use the normal form from :mod:`harness.normalform`.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Iterator, TextIO

from . import normalform

SCHEMA_VERSION = "0a"

# The schemas live at the repo root (the canonical, spec-facing location).
SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"

OPERATIONS = ("serialize", "deserialize")
STATUSES = ("ok", "error", "unsupported")


# --- envelopes --------------------------------------------------------------


@dataclass
class Request:
    operation: str
    case_id: str
    type: dict[str, Any] | None = None
    value: Any = None
    bytes_hex: str | None = None
    schema_version: str = SCHEMA_VERSION

    @classmethod
    def from_json(cls, obj: dict[str, Any]) -> "Request":
        return cls(
            operation=obj["operation"],
            case_id=obj["case_id"],
            type=obj.get("type"),
            value=obj.get("value"),
            bytes_hex=obj.get("bytes_hex"),
            schema_version=obj.get("schema_version", SCHEMA_VERSION),
        )

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "schema_version": self.schema_version,
            "operation": self.operation,
            "case_id": self.case_id,
        }
        if self.operation == "serialize":
            out["type"] = self.type
            out["value"] = self.value
        else:  # deserialize
            out["bytes_hex"] = self.bytes_hex
            out["type"] = self.type
        return out


@dataclass
class AdapterInfo:
    name: str
    version: str
    extra: dict[str, Any] | None = None

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"name": self.name, "version": self.version}
        if self.extra:
            out["extra"] = self.extra
        return out

    @classmethod
    def from_json(cls, obj: dict[str, Any]) -> "AdapterInfo":
        return cls(name=obj["name"], version=obj["version"], extra=obj.get("extra"))


@dataclass
class AdapterError:
    kind: str
    message: str

    def to_json(self) -> dict[str, Any]:
        return {"kind": self.kind, "message": self.message}

    @classmethod
    def from_json(cls, obj: dict[str, Any]) -> "AdapterError":
        return cls(kind=obj["kind"], message=obj["message"])


@dataclass
class Response:
    case_id: str
    operation: str
    adapter: AdapterInfo
    status: str = "ok"
    result: dict[str, Any] | None = None
    error: AdapterError | None = None
    schema_version: str = SCHEMA_VERSION

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "schema_version": self.schema_version,
            "case_id": self.case_id,
            "operation": self.operation,
            "adapter": self.adapter.to_json(),
            "status": self.status,
        }
        if self.result is not None:
            out["result"] = self.result
        if self.error is not None:
            out["error"] = self.error.to_json()
        return out

    @classmethod
    def from_json(cls, obj: dict[str, Any]) -> "Response":
        return cls(
            case_id=obj["case_id"],
            operation=obj["operation"],
            adapter=AdapterInfo.from_json(obj["adapter"]),
            status=obj.get("status", "ok"),
            result=obj.get("result"),
            error=AdapterError.from_json(obj["error"]) if obj.get("error") else None,
            schema_version=obj.get("schema_version", SCHEMA_VERSION),
        )


# --- convenience result constructors ---------------------------------------


def serialize_result(bytes_hex: str) -> dict[str, Any]:
    return {"bytes_hex": bytes_hex}


def deserialize_result(type_json: dict[str, Any], value: Any) -> dict[str, Any]:
    return {"type": type_json, "value": value}


# --- schema validation ------------------------------------------------------


@lru_cache(maxsize=None)
def _load_validator(name: str):
    import jsonschema

    schema = json.loads((SCHEMA_DIR / name).read_text())
    return jsonschema.Draft202012Validator(schema)


def validate_request(obj: dict[str, Any]) -> None:
    _load_validator("adapter-io.schema.json").validate({"request": obj})


def validate_response(obj: dict[str, Any]) -> None:
    _load_validator("adapter-io.schema.json").validate({"response": obj})


# --- streaming --------------------------------------------------------------


def read_requests(stream: TextIO, *, validate: bool = True) -> Iterator[Request]:
    """Yield :class:`Request` objects from a JSON Lines stream (blank lines
    skipped)."""
    for line in stream:
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        if validate:
            validate_request(obj)
        yield Request.from_json(obj)


def write_response(stream: TextIO, response: Response, *, validate: bool = True) -> None:
    obj = response.to_json()
    if validate:
        validate_response(obj)
    stream.write(json.dumps(obj) + "\n")
    stream.flush()


# --- adapter driver ---------------------------------------------------------

Handler = Callable[[Request], Response]


def run_adapter(
    adapter: AdapterInfo,
    handler: Handler,
    in_stream: TextIO | None = None,
    out_stream: TextIO | None = None,
    *,
    validate: bool = True,
) -> None:
    """Drive an adapter over JSON Lines stdin/stdout.

    ``handler`` maps a :class:`Request` to a :class:`Response`. Any exception it
    raises is captured as an ``error`` response so a single bad case never
    aborts the corpus run. This is the loop every adapter reuses, keeping
    "adding a participant = adding an adapter" true.
    """
    in_stream = in_stream or sys.stdin
    out_stream = out_stream or sys.stdout
    for request in read_requests(in_stream, validate=validate):
        try:
            response = handler(request)
        except Exception as exc:  # noqa: BLE001 - reported, not swallowed
            response = Response(
                case_id=request.case_id,
                operation=request.operation,
                adapter=adapter,
                status="error",
                error=AdapterError(kind=type(exc).__name__, message=str(exc)),
            )
        write_response(out_stream, response, validate=validate)


# Re-export so adapters can build value trees without a second import.
encode_value = normalform.encode_value
decode_value = normalform.decode_value
