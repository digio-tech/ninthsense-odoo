"""Turn the documents' extracted blocks into parsed values, one per key and document.

Each key is read from every one of its source documents, so a template's
mapping can later choose between them. A value is kept when it survives the
key's transform. Each document is read on its own, never from a merged view,
so a value always names the document it came from. When two documents share a
code, the first that yields a value is kept.

An Aadhaar number never leaves this module unmasked: it is reduced to its
last four digits, or to `unreadable` when it is not twelve digits.
"""

import dataclasses
import json

from .catalogue import ENTRIES
from .limits import Limits
from .masking import mask_aadhaar
from .transforms import apply_transform, clean_value

AADHAAR_KEY = "aadhaar_number"


@dataclasses.dataclass(frozen=True)
class DocInput:
    code: str
    extracted: dict | None


@dataclasses.dataclass(frozen=True)
class ExtractedValue:
    field_key: str
    label: str
    value: str
    source_code: str


def _dig(data: dict, path: str):
    current = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _text(value) -> str:
    if isinstance(value, dict | list):
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


def extract(documents: list[DocInput], limits: Limits) -> list[ExtractedValue]:
    """One value per catalogue key and source document, in catalogue then source order."""
    values: list[ExtractedValue] = []
    for entry in ENTRIES:
        for value, source_code in _source_values(entry, documents):
            if entry.key == AADHAAR_KEY:
                value = mask_aadhaar(value)
            values.append(
                ExtractedValue(
                    field_key=entry.key,
                    label=entry.label,
                    value=value[: limits.stored_value_max_length],
                    source_code=source_code,
                )
            )
    return values


def _source_values(entry, documents: list[DocInput]) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for code in dict.fromkeys(code for code, _path in entry.sources):
        paths = [path for source_code, path in entry.sources if source_code == code]
        value = _document_value(entry, code, paths, documents)
        if value is not None:
            found.append((value, code))
    return found


def _document_value(entry, code, paths, documents: list[DocInput]) -> str | None:
    for document in documents:
        if document.code != code or not isinstance(document.extracted, dict):
            continue
        for path in paths:
            raw = clean_value(_dig(document.extracted, path))
            if raw is None:
                continue
            transformed = apply_transform(raw, entry.transform)
            if transformed is None:
                continue
            text = _text(transformed)
            if text:
                return text
    return None
