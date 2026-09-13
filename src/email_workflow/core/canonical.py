from __future__ import annotations

import hashlib
from typing import Any

import jcs  # type: ignore[import-untyped]


def canonical_sha256(value: Any) -> str:
    """Return the SHA-256 digest of RFC 8785 canonical JSON."""
    return hashlib.sha256(jcs.canonicalize(value)).hexdigest()
