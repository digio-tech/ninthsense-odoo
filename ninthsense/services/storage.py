"""The only writer of what the wrapper delivers: documents, parsed values and results."""

import json

from ..core import bundle as core_bundle
from ..core import extraction, log
from ..core.limits import DEFAULT_LIMITS
from ..core.masking import mask_runs, mask_tree, national_phone

#: Bank account numbers are legitimately long digit runs and are never an Aadhaar number.
_UNSCRUBBED_KEYS = frozenset({"bank_ac_no"})
#: Phone numbers lose India's country code first, so a mobile is not mistaken for an Aadhaar.
_PHONE_KEYS = frozenset({"cell_number"})


def _stored_value(field_key, value):
    """A parsed value as it is kept: every Aadhaar-shaped run masked, bank numbers aside."""
    if field_key in _UNSCRUBBED_KEYS:
        return value
    if field_key in _PHONE_KEYS:
        value = national_phone(value)
    return mask_runs(value)


def _scrubbed_results(raw_bytes: bytes) -> str:
    """The delivered body as text, with no link token and no full Aadhaar number.

    The token is a live credential and only its hash is meant to be stored,
    so it is not kept in the results that officers can read.
    """
    body = json.loads(raw_bytes)
    if isinstance(body, dict):
        body.pop("token", None)
    return json.dumps(mask_tree(body), ensure_ascii=False)


def store_document(request, code, doc_id, file_name, content, mimetype, now):
    """Keep `content` as line `code`'s only document, replacing what the line or `doc_id` held.

    A line holds one document, the latest upload, so repeated uploads through
    one link cannot pile up files on the request.
    """
    request = request.sudo()
    env = request.env
    request.document_ids.filtered(
        lambda document: document.code == code or document.verification_document_id == doc_id
    ).unlink()
    attachment = env["ir.attachment"].create(
        {
            "name": mask_runs(file_name),
            "raw": content,
            "mimetype": mimetype,
            "res_model": request._name,
            "res_id": request.id,
        }
    )
    env["ninthsense.onboarding.document"].create(
        {
            "request_id": request.id,
            "code": code,
            "verification_document_id": doc_id,
            "attachment_id": attachment.id,
            "received_at": now,
        }
    )


def discard_document(request, doc_id):
    """Delete the stored document with this portal id, if there is one."""
    request = request.sudo()
    request.document_ids.filtered(
        lambda document: document.verification_document_id == doc_id
    ).unlink()


def accept_results(request, raw_bytes, bundle, now):
    """Record a verified completion bundle in one transaction.

    The raw body is kept without its token and with every Aadhaar-shaped run
    masked. The parsed values are replaced by those read from the bundle,
    documents the bundle does not name are deleted, and the request moves to
    `data_received`. A later bundle replaces all of this again.
    """
    request = request.sudo()
    env = request.env
    step = core_bundle.document_step(bundle)
    held = tuple(
        core_bundle.Held(document.code, document.verification_document_id)
        for document in request.document_ids
    )
    plan = core_bundle.plan(tuple(request.line_ids.mapped("code")), held, step.documents)

    values = extraction.extract(
        [
            extraction.DocInput(
                document.document_code,
                document.extracted if isinstance(document.extracted, dict) else None,
            )
            for document in plan.matched
        ],
        DEFAULT_LIMITS,
    )

    request.value_ids.unlink()
    env["ninthsense.onboarding.value"].create(
        [
            {
                "request_id": request.id,
                "field_key": value.field_key,
                "label": value.label,
                "value": _stored_value(value.field_key, value.value),
                "source_code": value.source_code,
            }
            for value in values
        ]
    )

    deleted = request.document_ids.filtered(
        lambda document: document.verification_document_id in plan.delete_ids
    )
    deleted_count = len(deleted)
    deleted.unlink()

    request.write(
        {
            "results_raw": _scrubbed_results(raw_bytes),
            "received_at": now,
            "state": "data_received",
        }
    )
    log.event(
        "results_accepted",
        outcome="ok",
        request_id=request.id,
        count=len(values),
        status=bundle.status.value,
    )
    if deleted_count:
        log.event("documents_removed", outcome="ok", request_id=request.id, count=deleted_count)
