from __future__ import annotations

import hashlib
import hmac


def signature_input(
    *,
    method: str,
    path: str,
    timestamp: str,
    idempotency_key: str,
    submission_request_id: str,
    content_sha256: str,
) -> bytes:
    return "\n".join(
        (
            method.upper(),
            path,
            timestamp,
            idempotency_key,
            submission_request_id,
            content_sha256,
        )
    ).encode("utf-8")


def sign_request(*, secret: str, **fields: str) -> str:
    return hmac.new(secret.encode("utf-8"), signature_input(**fields), hashlib.sha256).hexdigest()


def verify_signature(*, signature: str, secret: str, **fields: str) -> bool:
    expected = sign_request(secret=secret, **fields)
    return hmac.compare_digest(signature, expected)
