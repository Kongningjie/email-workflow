from __future__ import annotations

import hashlib
from typing import Any, cast

import jcs  # type: ignore[import-untyped]


def canonical_bytes(value: Any) -> bytes:
    """Serialize a value as RFC 8785 canonical JSON bytes."""
    return cast(bytes, jcs.canonicalize(value))


def canonical_sha256(value: Any) -> str:
    """Return the SHA-256 digest of RFC 8785 canonical JSON."""
    return hashlib.sha256(canonical_bytes(value)).hexdigest()
