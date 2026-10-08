"""The addon's settings, parsed from raw strings into values that are safe to use."""

from dataclasses import dataclass, field
from typing import Self
from urllib.parse import urlsplit

from .errors import NotConfigured

DEFAULT_LINK_VALIDITY_DAYS = 14
MIN_LINK_VALIDITY_DAYS = 1
MAX_LINK_VALIDITY_DAYS = 90
MIN_SECRET_LENGTH = 32

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1"})


def _is_local_host(host: str) -> bool:
    """True for the loopback names, including any subdomain of `localhost`.

    Names under `.localhost` always resolve to the local machine, and a
    multi-tenant portal running locally serves each tenant on one of them.
    """
    return host in _LOCAL_HOSTS or host.endswith(".localhost")


@dataclass(frozen=True)
class Config:
    """`portal_url` and `secret` are `None` when unset or unusable."""

    portal_url: str | None
    secret: str | None = field(repr=False)
    link_validity_days: int

    def require_ready(self) -> Self:
        """Return `self`, or raise `NotConfigured` naming which of the two is missing."""
        if not self.portal_url or not self.secret:
            raise NotConfigured(
                "the portal url or secret is not set",
                context={"portal_url": bool(self.portal_url), "secret": bool(self.secret)},
            )
        return self


def _clean_portal_url(value, allow_insecure_localhost: bool) -> str | None:
    """The origin to link to, or `None` when it is blank or not an acceptable origin.

    Only a bare origin is accepted: a path, query or fragment would be
    appended to by the link builder and silently point somewhere else.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parts = urlsplit(value.strip())
        host = parts.hostname
    except ValueError:
        return None
    if not host or parts.username or parts.password:
        return None
    if parts.path not in ("", "/") or parts.query or parts.fragment:
        return None
    local_http = parts.scheme == "http" and allow_insecure_localhost and _is_local_host(host)
    if parts.scheme != "https" and not local_http:
        return None
    return f"{parts.scheme}://{parts.netloc}"


def _clean_secret(value) -> str | None:
    if isinstance(value, str) and len(value) >= MIN_SECRET_LENGTH:
        return value
    return None


def _clean_days(value) -> int:
    if value is None or (isinstance(value, str) and not value.strip()):
        return DEFAULT_LINK_VALIDITY_DAYS
    try:
        days = int(value) if not isinstance(value, bool) else None
    except (TypeError, ValueError):
        days = None
    if days is None or not MIN_LINK_VALIDITY_DAYS <= days <= MAX_LINK_VALIDITY_DAYS:
        raise NotConfigured(
            "the link validity must be a whole number of days from "
            f"{MIN_LINK_VALIDITY_DAYS} to {MAX_LINK_VALIDITY_DAYS}",
            context={"link_validity_days": False},
        )
    return days


def parse(portal_url, secret, link_validity_days, allow_insecure_localhost: bool = False) -> Config:
    """Validate raw settings into a `Config`.

    An unusable portal url or a secret shorter than 32 characters reads as
    not set, so `require_ready()` reports it. A link validity that is set
    but is not a whole number of days from 1 to 90 raises `NotConfigured`
    straight away, because falling back to the default would hide a typo.
    """
    return Config(
        portal_url=_clean_portal_url(portal_url, allow_insecure_localhost),
        secret=_clean_secret(secret),
        link_validity_days=_clean_days(link_validity_days),
    )
