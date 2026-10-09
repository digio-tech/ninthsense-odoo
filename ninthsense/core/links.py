"""Portal link tokens: minting, hashing, and the state a link is in.

A link's token is never stored; only its SHA-256 is. The candidate portal is
handed the token once, in the invite, and every later call proves the same
token by hashing it again.
"""

import datetime
import hashlib
import re
import secrets

from .errors import InvalidToken
from .limits import Limits

_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def mint_token() -> str:
    """A fresh, URL-safe token for a new portal link."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """The SHA-256 hex digest stored in place of the token itself."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def parse_token(value: str, limits: Limits) -> str:
    """Validate an inbound token's shape and return it unchanged.

    Raises `InvalidToken` for anything empty, longer than
    `limits.token_max_length`, or outside `[A-Za-z0-9_-]`. This is a shape
    check only; resolving the token to a request is the caller's job.
    """
    if not isinstance(value, str) or not value:
        raise InvalidToken("token is missing")
    if len(value) > limits.token_max_length:
        raise InvalidToken("token is too long")
    if not _TOKEN_RE.match(value):
        raise InvalidToken("token has disallowed characters")
    return value


def portal_state(
    state: str,
    expires_at: datetime.datetime | None,
    now: datetime.datetime,
) -> str:
    """The state the candidate portal should see: `open`, `submitted`, `expired` or `revoked`.

    `state` is the request's own workflow state. Once results have been
    received (`data_received`) the link reads as submitted whatever its
    expiry. A request that was completed or cancelled no longer honours the
    link at all, so it reads as revoked. Only a request still waiting on the
    candidate (`link_sent`) can be open, and it turns expired once `now` is
    past `expires_at`.
    """
    if state == "data_received":
        return "submitted"
    if state != "link_sent":
        return "revoked"
    if expires_at is not None and now > expires_at:
        return "expired"
    return "open"


def expiry(now: datetime.datetime, link_validity_days: int) -> datetime.datetime:
    """The expiry to stamp on a freshly minted link."""
    return now + datetime.timedelta(days=link_validity_days)
