"""HMAC verification for the candidate portal's completion callback.

The callback carries `X-Portal-Signature: t=<unix_seconds>,v1=<hex_sha256>`,
computed by the portal over the exact bytes it puts on the wire. This module
is the only thing that decides whether a delivery is genuine; it takes the
raw body, the header, the configured secret and the clock as plain values,
so it can be tested without anything else.
"""

import hashlib
import hmac
import re

from .errors import BadSignature
from .limits import Limits

_HEADER_RE = re.compile(r"^t=(\d{1,20}),v1=([0-9a-f]{64})$")


def verify(header: str | None, raw: bytes, secret: str, now: int, limits: Limits) -> None:
    """Raise `BadSignature` unless `header` is a genuine signature over `raw`.

    Every failure - a missing or malformed header, a timestamp outside
    `limits.signature_skew_seconds`, no secret, or a digest that does not
    match - raises the same error type, deliberately carrying no detail about
    which check failed.
    """
    if not header:
        raise BadSignature("missing signature header")

    match = _HEADER_RE.match(header)
    if not match:
        raise BadSignature("malformed signature header")

    timestamp_text, digest = match.group(1), match.group(2)

    if abs(now - int(timestamp_text)) > limits.signature_skew_seconds:
        raise BadSignature("signature timestamp outside allowed skew")

    if not secret:
        raise BadSignature("no signing secret configured")

    signed_content = f"{timestamp_text}.".encode() + raw
    expected = hmac.new(secret.encode("utf-8"), signed_content, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, digest):
        raise BadSignature("signature does not match the configured secret")
