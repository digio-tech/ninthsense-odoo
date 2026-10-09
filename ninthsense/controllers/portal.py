import functools
import hmac
import json
import mimetypes
import time
from pathlib import Path

from odoo import fields, http
from odoo.exceptions import ConcurrencyError
from odoo.http import request
from odoo.sql_db import PG_CONCURRENCY_EXCEPTIONS_TO_RETRY
from odoo.tools.mimetypes import guess_mimetype

from ..core import descriptor as core_descriptor
from ..core import links, log, portal_contract, signature
from ..core.errors import (
    BadSignature,
    DescriptorInvalid,
    FileTypeNotAllowed,
    InvalidPayload,
    InvalidToken,
    NinthsenseError,
    NotOpen,
    UnknownDocument,
)
from ..core.limits import DEFAULT_LIMITS
from ..models.onboarding_request import OPEN_STATES
from ..services import config as ns_config
from ..services import storage

_PREFIX = "/api/method/ninthsense.document_collection.portal_api."
_ROUTE_OPTIONS = {
    "type": "http",
    "auth": "public",
    "csrf": False,
    "save_session": False,
}
_SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"
_BYTES_PER_MB = 1024 * 1024
_NAME_MAX_LENGTH = 120

#: Failures Odoo answers by running the whole call again, so they are not turned into a reply.
_RETRIED = (*PG_CONCURRENCY_EXCEPTIONS_TO_RETRY, ConcurrencyError)

_SERVER_ERROR = (500, "server_error")
#: HTTP status and error code for each failure the portal can be told about.
#: A request that is not open is indistinguishable from an unknown link.
_ERROR_STATUS = {
    InvalidToken: (404, "invalid_token"),
    NotOpen: (404, "invalid_token"),
    BadSignature: (401, "bad_signature"),
    InvalidPayload: (400, "invalid_payload"),
    UnknownDocument: (400, "unknown_document"),
    FileTypeNotAllowed: (415, "file_type_not_allowed"),
    DescriptorInvalid: _SERVER_ERROR,
}


@functools.cache
def validators():
    """The vendored portal schemas, loaded once per process."""
    return portal_contract.load_validators(_SCHEMA_DIR)


def error_response(err):
    status, code = _ERROR_STATUS.get(type(err), _SERVER_ERROR)
    return request.make_json_response({"error": {"code": code}}, status=status)


def _ok():
    return request.make_json_response({"ok": True})


def _resolve(token_value):
    """The request a token belongs to, or `InvalidToken`.

    A request that is no longer waiting on the candidate reads as an unknown
    link, whatever hash it still carries.
    """
    token = links.parse_token(token_value, DEFAULT_LIMITS)
    digest = links.hash_token(token)
    found = (
        request.env["ninthsense.onboarding.request"]
        .sudo()
        .search([("link_hash", "=", digest), ("state", "in", OPEN_STATES)], limit=2)
    )
    if len(found) != 1 or not hmac.compare_digest(found.link_hash or "", digest):
        raise InvalidToken("unknown link")
    return found


def _require_open(onboarding_request):
    if onboarding_request._ninthsense_portal_state(fields.Datetime.now()) != "open":
        raise NotOpen("link is not open", context={"state": onboarding_request.state})


def _edge(route, token_getter, handler, *, signed=False):
    """Run one portal call: log it, authenticate it, and map every failure to its reply.

    A concurrency failure is the exception: it propagates, so that Odoo rolls
    back and runs the call again.

    `token_getter` is only called once a signed call's signature has been
    verified, so an unsigned delivery never reaches the token lookup.
    """
    started = time.monotonic()
    correlation_id = log.new_correlation_id(request.httprequest.headers.get("X-Request-Id"))
    log.event("portal_call", outcome="start", correlation_id=correlation_id, route=route)
    onboarding_request = None
    reason_code = None
    raised_at = None
    try:
        with request.env.cr.savepoint():
            if signed:
                signature.verify(
                    request.httprequest.headers.get("X-Portal-Signature"),
                    request.httprequest.get_data(),
                    ns_config.load(request.env).secret or "",
                    int(time.time()),
                    DEFAULT_LIMITS,
                )
            onboarding_request = _resolve(token_getter())
            response = handler(onboarding_request)
        outcome = "ok"
    except _RETRIED as err:
        log.event(
            "portal_call",
            outcome="retried",
            correlation_id=correlation_id,
            route=route,
            reason_code=type(err).__name__,
        )
        raise
    except NinthsenseError as err:
        response = error_response(err)
        outcome = err.code
    except Exception as err:
        response = error_response(err)
        outcome = "server_error"
        reason_code = type(err).__name__
        raised_at = log.where(err)
    log.event(
        "portal_call",
        outcome=outcome,
        correlation_id=correlation_id,
        duration_ms=round((time.monotonic() - started) * 1000, 1),
        route=route,
        http_status=response.status_code,
        request_id=onboarding_request.id if onboarding_request else None,
        reason_code=reason_code,
        where=raised_at,
    )
    return response


def _completion_token():
    try:
        envelope = json.loads(request.httprequest.get_data())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise InvalidPayload("malformed json body") from exc
    return envelope.get("token") if isinstance(envelope, dict) else None


def _allowed_mimetypes(extensions):
    allowed = set()
    for extension in extensions:
        guessed, _encoding = mimetypes.guess_type(f"file{extension}")
        if guessed == "application/pdf" or (guessed or "").startswith("image/"):
            allowed.add(guessed)
    return allowed


def _document_id(form):
    doc_id = form.get("verification_document_id") or ""
    max_length = DEFAULT_LIMITS.verification_document_id_max_length
    if not 1 <= len(doc_id) <= max_length or not doc_id.isprintable():
        raise InvalidPayload("verification_document_id is malformed")
    return doc_id


def _descriptor(onboarding_request, now):
    """The descriptor for this request, built from its own record and its company."""
    company = onboarding_request.company_id
    base_url = request.env["ir.config_parameter"].sudo().get_str("web.base.url", "")
    first_names = (onboarding_request.applicant_name or "").split()
    held = {}
    for document in onboarding_request.document_ids:
        held[document.code] = document.verification_document_id
    request_view = core_descriptor.RequestView(
        ref=onboarding_request.ref,
        expires_at=onboarding_request.link_expires_at or None,
        instance_url=base_url,
        display_name=first_names[0][:_NAME_MAX_LENGTH] if first_names else None,
    )
    lines = [
        core_descriptor.LineView(
            code=line.code,
            label=line.label,
            order=position,
            mandatory=bool(line.mandatory),
            accept=core_descriptor.accept_extensions(line.accept),
            max_mb=line.max_mb,
            verification_document_id=held.get(line.code),
        )
        for position, line in enumerate(onboarding_request.line_ids, start=1)
    ]
    branding = core_descriptor.Branding(
        org_name=(company.name or "")[:1024] or None,
        logo_url=f"{base_url}/logo.png?company={company.id}" if company.logo else None,
    )
    return core_descriptor.build(
        request_view, lines, onboarding_request._ninthsense_portal_state(now), branding
    )


class NinthsensePortal(http.Controller):
    @http.route(_PREFIX + "get_request", methods=["GET"], readonly=True, **_ROUTE_OPTIONS)
    def get_request(self, **kwargs):
        def handler(onboarding_request):
            now = fields.Datetime.now()
            if onboarding_request._ninthsense_portal_state(now) == "expired":
                raise InvalidToken("link has expired")
            descriptor = _descriptor(onboarding_request, now)
            try:
                portal_contract.validate_descriptor(validators(), descriptor)
            except InvalidPayload as err:
                raise DescriptorInvalid("descriptor failed its own schema") from err
            return request.make_json_response(descriptor)

        return _edge("get_request", lambda: request.httprequest.args.get("token"), handler)

    @http.route(_PREFIX + "store_document", methods=["POST"], **_ROUTE_OPTIONS)
    def store_document(self, **kwargs):
        form = request.httprequest.form

        def handler(onboarding_request):
            _require_open(onboarding_request)
            code = form.get("document_code") or ""
            line = onboarding_request.line_ids.filtered(lambda line: line.code == code)
            if not line:
                raise UnknownDocument("document_code is not on this request")
            doc_id = _document_id(form)
            upload = request.httprequest.files.get("file")
            if upload is None:
                raise InvalidPayload("file is missing")
            max_bytes = line.max_mb * _BYTES_PER_MB
            # One byte over the limit is enough to refuse, so no more is read.
            content = upload.read(max_bytes + 1)
            file_name = upload.filename or f"{code}.bin"
            extensions = core_descriptor.accept_extensions(line.accept)
            if len(content) > max_bytes:
                raise FileTypeNotAllowed("file is over the size limit")
            if not any(file_name.lower().endswith(extension) for extension in extensions):
                raise FileTypeNotAllowed("file extension is not accepted")
            mimetype = guess_mimetype(content, default="")
            if mimetype not in _allowed_mimetypes(extensions):
                raise FileTypeNotAllowed("file content is not an accepted type")
            storage.store_document(
                onboarding_request,
                code,
                doc_id,
                file_name,
                content,
                mimetype,
                fields.Datetime.now(),
            )
            return _ok()

        return _edge("store_document", lambda: form.get("token"), handler)

    @http.route(_PREFIX + "discard_document", methods=["POST"], **_ROUTE_OPTIONS)
    def discard_document(self, **kwargs):
        form = request.httprequest.form

        def handler(onboarding_request):
            _require_open(onboarding_request)
            storage.discard_document(onboarding_request, _document_id(form))
            return _ok()

        return _edge("discard_document", lambda: form.get("token"), handler)

    @http.route(_PREFIX + "store_verification", methods=["POST"], **_ROUTE_OPTIONS)
    def store_verification(self, **kwargs):
        def handler(onboarding_request):
            raw = request.httprequest.get_data()
            _token, bundle = portal_contract.parse_completion(validators(), raw)
            if bundle.ref != onboarding_request.ref:
                raise InvalidPayload("payload ref does not match this request")
            storage.accept_results(onboarding_request, raw, bundle, fields.Datetime.now())
            return _ok()

        return _edge("store_verification", _completion_token, handler, signed=True)
