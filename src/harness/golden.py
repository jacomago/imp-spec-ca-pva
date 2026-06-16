"""Oracle v1 — golden fixtures (Phase 0b).

A *golden fixture* pairs an EPICS spec's authoritative hex example with a
**hand-verified** decoding and a citation. Together they are the adjudicator the
roadmap calls oracle v1: when independent implementations disagree, the fixtures
say which (if either) matches the spec.

Fixtures are authored *from the spec hex* — never snapshotted from an
implementation's output, which would let an implementation define truth. There
is no PVA/CA codec in the repo yet (those arrive in Phase 2/4), so the
hex<->decoding link is established by hand and by citation; this module and
:mod:`tests.test_golden` check everything *around* that link:

* the envelope is shape-valid (``schemas/fixture.schema.json``);
* an embedded normal-form document conforms (``harness.normalform.validate``)
  and round-trips idempotently;
* every hex segment is well-formed.

PVA serializes the *type* (FieldDesc) and the *value* separately, and BitSet /
Status are compact meta-encodings, so a fixture's ``decoded`` is one of three
shapes — an introspection-only **type tree**, a complete **normal-form
document**, or a **meta** payload (``bitset`` / ``status``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from . import normalform

# Fixtures live at the repo root (spec-facing ground truth, a sibling of
# schemas/), grouped by protocol: fixtures/<protocol>/<case>.json.
FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "fixtures"
SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"


class FixtureError(ValueError):
    """Raised when a fixture file is malformed or fails validation."""


def canonical_hex(hex_str: str) -> str:
    """Strip whitespace and lower-case a (possibly space-grouped) hex string.

    Fixtures may store bytes grouped the way the spec prints them
    (``"FD 00 01 80"``); the canonical form has no spaces and is lower-case."""
    out = "".join(hex_str.split()).lower()
    if len(out) % 2 != 0:
        raise FixtureError(f"hex has an odd number of digits: {hex_str!r}")
    return out


def hex_to_bytes(hex_str: str) -> bytes:
    return bytes.fromhex(canonical_hex(hex_str))


@dataclass(frozen=True)
class Fixture:
    case_id: str
    protocol: str
    byte_order: str
    source: dict[str, Any]
    segments: dict[str, str]
    decoded: dict[str, Any]
    path: Path

    @property
    def normal_form(self) -> dict[str, Any] | None:
        """The embedded normal-form document, if ``decoded`` is one."""
        return self.decoded if "schema_version" in self.decoded else None

    @property
    def type_tree(self) -> dict[str, Any] | None:
        """The introspection-only type tree, if that is what ``decoded`` holds."""
        if "schema_version" in self.decoded or "meta" in self.decoded:
            return None
        return self.decoded.get("type")

    @property
    def meta(self) -> dict[str, Any] | None:
        """The BitSet/Status meta payload, if that is what ``decoded`` holds."""
        return self.decoded.get("meta")

    def segment_bytes(self, name: str) -> bytes:
        return hex_to_bytes(self.segments[name])


# --- schema validation ------------------------------------------------------


@lru_cache(maxsize=None)
def _validator():
    import jsonschema

    schema = json.loads((SCHEMA_DIR / "fixture.schema.json").read_text())
    return jsonschema.Draft202012Validator(schema)


def validate_fixture(obj: dict[str, Any]) -> None:
    """Validate a fixture object against ``fixture.schema.json`` (shape only)."""
    _validator().validate(obj)


# --- loading ----------------------------------------------------------------


def load_fixture(path: Path, *, validate: bool = True) -> Fixture:
    obj = json.loads(Path(path).read_text())
    if validate:
        validate_fixture(obj)
    return Fixture(
        case_id=obj["case_id"],
        protocol=obj["protocol"],
        byte_order=obj["byte_order"],
        source=obj["source"],
        segments=obj["segments"],
        decoded=obj["decoded"],
        path=Path(path),
    )


def load_fixtures(directory: Path | str = FIXTURES_ROOT, *, validate: bool = True) -> list[Fixture]:
    """Load every ``*.json`` fixture under ``directory`` (recursively), sorted by
    path for a stable order."""
    root = Path(directory)
    return [load_fixture(p, validate=validate) for p in sorted(root.rglob("*.json"))]
