"""Builds the candidate-portal descriptor served by `get_request`.

The output maps onto `schemas/request.schema.json` (descriptor version 2.0).
This module only shapes data: the caller resolves its own records into the
small dataclasses below, and validates the result with
`core.portal_contract.validate_descriptor`.
"""

import datetime
from dataclasses import dataclass

from .portal_contract import EMITTED_DESCRIPTOR_VERSION

#: `hrms.system`, per the portal contract: free text, never read back.
HRMS_SYSTEM = "odoo"

#: Every request this addon sends is the onboarding goal.
GOAL_KEY = "onboarding"
STAGE_LABEL = "Onboarding"

#: Identifies the set of document types the catalogue reads.
CATALOGUE_VERSION = 1

#: Where the candidate portal posts the completion bundle. Fixed by the
#: contract's callback path allow-list.
CALLBACK_PATH = "/api/method/ninthsense.document_collection.portal_api.store_verification"

_BYTES_PER_MB = 1024 * 1024


@dataclass(frozen=True)
class RequestView:
    """One onboarding request, as the descriptor needs it.

    ref: the request's reference, echoed back in the completion bundle.
    expires_at: the link's expiry, or None to omit `expires_at` entirely.
    instance_url: this Odoo instance's base URL, echoed as `hrms.instance`.
    display_name: the candidate's first name, or None to omit
        `subject.display_name`.
    """

    ref: str
    expires_at: datetime.datetime | None
    instance_url: str
    display_name: str | None = None


@dataclass(frozen=True)
class LineView:
    """One requested document line, in the order it should appear.

    code: the stable document code.
    label: what the candidate sees for this line.
    order: the line's position.
    mandatory: whether the line is required.
    accept: file extensions this line accepts, each starting with a dot.
    max_mb: the size cap in megabytes; the descriptor carries `max_bytes`.
    verification_document_id: the portal's id of the document currently
        filed on this line, or None when the line is empty.
    """

    code: str
    label: str
    order: int
    mandatory: bool
    accept: tuple[str, ...]
    max_mb: int
    verification_document_id: str | None


@dataclass(frozen=True)
class Branding:
    """Portal branding. Every field is optional and omitted when unset."""

    org_name: str | None = None
    logo_url: str | None = None


def accept_extensions(text: str | None) -> tuple[str, ...]:
    """The comma-separated `accept` text as lower-case, dot-prefixed extensions."""
    extensions: list[str] = []
    for part in (text or "").split(","):
        extension = part.strip().lower()
        if not extension:
            continue
        if not extension.startswith("."):
            extension = "." + extension
        if extension not in extensions:
            extensions.append(extension)
    return tuple(extensions)


def _iso_z(value: datetime.datetime) -> str:
    dt = value
    if dt.tzinfo is not None:
        dt = dt.astimezone(datetime.UTC).replace(tzinfo=None)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _branding_dict(branding: Branding) -> dict:
    out = {}
    if branding.org_name:
        out["org_name"] = branding.org_name
    if branding.logo_url:
        out["logo_url"] = branding.logo_url
    return out


def _document(line: LineView) -> dict:
    document = {
        "document_code": line.code,
        "label": line.label,
        "order": line.order,
        "mandatory": line.mandatory,
        "accept": list(line.accept),
        "max_bytes": line.max_mb * _BYTES_PER_MB,
    }
    if line.verification_document_id:
        document["verification_document_id"] = line.verification_document_id
    return document


def build(
    request_view: RequestView,
    lines: list[LineView],
    state: str,
    branding: Branding,
) -> dict:
    """Build one descriptor dict, ready for `portal_contract.validate_descriptor`.

    `state` is the already-computed portal state (`open`, `submitted` or
    `expired`). Only `open` carries documents, in the order `lines` is given
    in; every other state gets an empty `document_collection` step, per the
    portal contract.
    """
    step: dict = {
        "id": "docs",
        "type": "document_collection",
        "documents": [_document(line) for line in lines] if state == "open" else [],
    }

    descriptor = {
        "schema_version": EMITTED_DESCRIPTOR_VERSION,
        "ref": request_view.ref,
        "hrms": {"system": HRMS_SYSTEM, "instance": request_view.instance_url},
        "goal_key": GOAL_KEY,
        "stage": STAGE_LABEL,
        "catalogue_version": CATALOGUE_VERSION,
        "state": state,
        "branding": _branding_dict(branding),
        "steps": [step],
        "completion": {"callback_path": CALLBACK_PATH},
    }

    if request_view.expires_at is not None:
        descriptor["expires_at"] = _iso_z(request_view.expires_at)

    if request_view.display_name:
        descriptor["subject"] = {"display_name": request_view.display_name}

    return descriptor
