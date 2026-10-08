"""Shared builders for the tests that drive the wrapper's portal routes."""

import hashlib
import hmac
import json
import time

from odoo import fields

from ..services import config as ns_config
from ..services import invitations
from .test_send import PORTAL_URL, SECRET, configure_portal, default_template

PREFIX = "/api/method/ninthsense.document_collection.portal_api."
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PDF_BYTES = b"%PDF-1.4\n%test\n" + b"0" * 64
MB = 1024 * 1024


def sign(secret, timestamp, body):
    """The `X-Portal-Signature` header value the wrapper would send for `body`."""
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


def signed_headers(body, secret=SECRET, timestamp=None):
    timestamp = int(time.time()) if timestamp is None else timestamp
    return {
        "Content-Type": "application/json",
        "X-Portal-Signature": sign(secret, timestamp, body),
    }


def envelope(token, payload):
    return json.dumps({"token": token, "payload": payload}, separators=(",", ":")).encode()


def completion_document(code, doc_id, extracted, status="done"):
    return {
        "document_code": code,
        "verification_document_id": doc_id,
        "status": status,
        "confidence": 0.93,
        "low_confidence": False,
        "file_name": f"{code}.png",
        "extracted": extracted,
    }


def completion_payload(request, documents, status="completed"):
    return {
        "schema_version": "2.0",
        "ref": request.ref,
        "goal_key": "onboarding",
        "stage": "Onboarding",
        "catalogue_version": 1,
        "status": status,
        "completed_at": "2026-09-29T10:15:02Z",
        "steps": [
            {
                "id": "docs",
                "type": "document_collection",
                "provider": {"name": "9thsense", "session_id": "case_42", "case_status": status},
                "result": {"cross_match": "passed"},
                "documents": documents,
                "missing_documents": [],
            }
        ],
    }


def send_link(env, applicant, template=None):
    """Send the onboarding link the way the button does. Returns `(request, token)`."""
    configure_portal(env)
    template = template or default_template(env)
    request, url = invitations.send(applicant, ns_config.load(env), template, fields.Datetime.now())
    return request, url.removeprefix(f"{PORTAL_URL}/s/")


def post_documents(case, request, token):
    """Upload a file for every mandatory line, as the wrapper does for the candidate."""
    for line in request.line_ids.filtered("mandatory"):
        pdf_only = line.accept == ".pdf"
        response = case.url_open(
            PREFIX + "store_document",
            files={
                "token": (None, token),
                "document_code": (None, line.code),
                "verification_document_id": (None, f"doc_{line.code}"),
                "file": (
                    "scan.pdf" if pdf_only else "scan.png",
                    PDF_BYTES if pdf_only else PNG_BYTES,
                    "application/octet-stream",
                ),
            },
        )
        case.assertEqual(response.status_code, 200, response.text)


def post_verification(case, request, token, extracted_by_code, result=None):
    """Deliver the signed parsed result for every mandatory line."""
    documents = [
        completion_document(line.code, f"doc_{line.code}", extracted_by_code.get(line.code, {}))
        for line in request.line_ids.filtered("mandatory")
    ]
    payload = completion_payload(request, documents)
    if result is not None:
        payload["steps"][0]["result"] = result
    raw = envelope(token, payload)
    response = case.url_open(PREFIX + "store_verification", data=raw, headers=signed_headers(raw))
    case.assertEqual(response.status_code, 200, response.text)
