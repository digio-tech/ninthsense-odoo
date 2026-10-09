"""Matching a completion bundle's documents to the documents and lines already held.

Pure computation over plain values: the caller reads its own records into the
small dataclasses below and applies the plan this module returns.
"""

from dataclasses import dataclass

from . import contract_types as ct

#: The provider's code for a document it could not resolve to any line.
#: Never a real document code.
UNFILED = "unfiled"

_DOCUMENT_STEP = "document_collection"


@dataclass(frozen=True)
class Held:
    """A document already stored on the request."""

    code: str
    verification_document_id: str


@dataclass(frozen=True)
class Plan:
    """What accepting a bundle requires of the caller's records.

    matched: the bundle's documents that belong to a line of the request, in
        bundle order. These are the ones values are read from.
    delete_ids: portal ids of stored documents the bundle does not name.
    """

    matched: tuple[ct.Document, ...]
    delete_ids: tuple[str, ...]


def document_step(bundle: ct.CompletionPayload) -> ct.CompletionStep:
    """The bundle's document-collection step, or its first step if none is labelled so."""
    return next((step for step in bundle.steps if step.type == _DOCUMENT_STEP), bundle.steps[0])


def plan(line_codes: tuple[str, ...], held: tuple[Held, ...], documents: list[ct.Document]) -> Plan:
    """Match `documents` to the request's lines by code and find what to delete.

    A bundle entry coded `unfiled` or with a code that is not on any line is
    never matched, so nothing is read from it. A stored document is kept when
    its id appears anywhere in the bundle, `unfiled` entries included: the
    provider saw the file, it just could not place it, and the file is the
    only copy HR has.
    """
    named = {document.verification_document_id for document in documents}
    matched = tuple(
        document
        for document in documents
        if document.document_code != UNFILED and document.document_code in line_codes
    )
    return Plan(
        matched=matched,
        delete_ids=tuple(
            item.verification_document_id
            for item in held
            if item.verification_document_id not in named
        ),
    )
