"""Shared, pure-Python harness library for the ca-pva machine spec.

No EPICS dependencies live here — this package is the dependency-light core that
the conformance consumer and every adapter build on.

* :mod:`harness.normalform` — contract #2, the canonical normal form.
* :mod:`harness.io` — the adapter stdin/stdout (JSON Lines) I/O contract.
"""

from . import io, normalform

__all__ = ["normalform", "io"]
