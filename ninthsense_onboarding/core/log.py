import json
import logging
import re
import uuid

_logger = logging.getLogger("odoo.addons.ninthsense_onboarding")

_CORRELATION_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

ALLOWED_KEYS = frozenset(
    {
        "request_id",
        "applicant_id",
        "employee_id",
        "attachment_id",
        "state",
        "status",
        "count",
        "reason_code",
        "route",
        "http_status",
        "where",
    }
)


def new_correlation_id(inbound: str | None) -> str:
    if inbound and _CORRELATION_ID_RE.match(inbound):
        return inbound
    return str(uuid.uuid4())


def where(error: BaseException) -> str | None:
    """`module:function:line` of the frame that raised `error`, and nothing of its message."""
    trace = error.__traceback__
    if trace is None:
        return None
    while trace.tb_next is not None:
        trace = trace.tb_next
    frame = trace.tb_frame
    return f"{frame.f_globals.get('__name__', '?')}:{frame.f_code.co_name}:{trace.tb_lineno}"


def event(
    name: str,
    *,
    outcome: str,
    correlation_id: str | None = None,
    duration_ms: float | None = None,
    **fields,
) -> None:
    record = {"event": name, "outcome": outcome}
    if correlation_id is not None:
        record["correlation_id"] = correlation_id
    if duration_ms is not None:
        record["duration_ms"] = duration_ms
    for key, value in fields.items():
        if key in ALLOWED_KEYS:
            record[key] = value
    _logger.info(json.dumps(record, sort_keys=True, default=str))


#: Odoo logs every HTTP request line, query string included, through this
#: logger. A portal call's query string carries a live, still-usable link token.
ACCESS_LOGGER_NAME = "odoo.http.server"
_LOGGED_PATH_MARKER = "/api/method/ninthsense."
_TOKEN_IN_QUERY = re.compile(r"(token=)[^&\s\"]+")
#: Record attributes the access log formats the request line into, beside `msg`.
_REQUEST_LINE_ATTRIBUTES = ("colored_message", "http_request_line")


def _redact(text):
    if isinstance(text, str) and _LOGGED_PATH_MARKER in text and "token=" in text:
        return _TOKEN_IN_QUERY.sub(r"\1***", text)
    return text


class TokenRedactingFilter(logging.Filter):
    """Rewrites a portal route's `token=...` query value out of an access log record."""

    def filter(self, record):
        message = record.getMessage()
        redacted = _redact(message)
        if redacted is not message:
            record.msg = redacted
            record.args = ()
        for name in _REQUEST_LINE_ATTRIBUTES:
            value = getattr(record, name, None)
            if value is not None:
                setattr(record, name, _redact(value))
        return True


def access_logger():
    return logging.getLogger(ACCESS_LOGGER_NAME)


def install_token_filter() -> None:
    """Add the filter to Odoo's access logger, once however often this is called."""
    logger = access_logger()
    if any(type(existing).__name__ == TokenRedactingFilter.__name__ for existing in logger.filters):
        return
    logger.addFilter(TokenRedactingFilter())
