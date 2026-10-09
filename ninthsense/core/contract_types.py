# request.schema.json sha256=ea71c028d133f09f804394b02cf2f4d13669843f8f5f109328e999d2353ed493
# completion.schema.json sha256=cc3a2844535617d00f98fed20d3eb593ff3a64d0b298e813c2c864dec7dbba84

from dataclasses import dataclass
from enum import Enum
from typing import Any


class Status(Enum):
    completed = "completed"
    review = "review"
    failed = "failed"


@dataclass
class Provider:
    name: str
    session_id: str
    case_status: str


@dataclass
class Document:
    document_code: str
    verification_document_id: str
    status: str
    doc_index: int | None = None
    detected_document_type: str | None = None
    is_detected_type_expected: bool | None = None
    confidence: float | None = None
    low_confidence: bool | None = None
    file_name: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    extracted: dict[str, Any] | list[Any] | str | float | bool | None = None


@dataclass
class CompletionStep:
    id: str
    type: str
    provider: Provider
    documents: list[Document]
    missing_documents: list[str]
    result: dict[str, Any] | list[Any] | str | float | bool | None = None
    extractions: dict[str, Any] | list[Any] | str | float | bool | None = None


@dataclass
class CompletionPayload:
    schema_version: str
    ref: str
    goal_key: str
    stage: str
    catalogue_version: int
    status: Status
    completed_at: str
    steps: list[CompletionStep]
