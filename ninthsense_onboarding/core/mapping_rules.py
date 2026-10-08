"""The rules a template's field mapping must follow, and the value each mapped key takes.

A mapping row is a `(key, source_code, fallback_code)` tuple: the catalogue
key, the document the value is read from, and the document read when the
source has no value. The fallback may be `None`. A row may only name
documents that are in the template and that the catalogue lists as sources
for its key.
"""

from collections import Counter
from dataclasses import dataclass

from .catalogue import CATALOGUE, ENTRIES

UNKNOWN_FIELD = "unknown_field"
MAPPED_TWICE = "mapped_twice"
SOURCE_NOT_ALLOWED = "source_not_allowed"
FALLBACK_NOT_ALLOWED = "fallback_not_allowed"
FALLBACK_IS_SOURCE = "fallback_is_source"


@dataclass(frozen=True)
class Problem:
    kind: str
    key: str


def allowed_sources(key, template_codes) -> tuple[str, ...]:
    """The template's documents that can supply `key`, in the catalogue's source order."""
    entry = CATALOGUE.get(key)
    if entry is None:
        return ()
    present = set(template_codes)
    return tuple(dict.fromkeys(code for code, _path in entry.sources if code in present))


def mapping_problems(rows, template_codes) -> list[Problem]:
    """Every reason the rows break the mapping rules for a template with these documents."""
    problems: list[Problem] = []
    counts = Counter(key for key, _source, _fallback in rows)
    reported_twice = set()
    for key, source, fallback in rows:
        if key not in CATALOGUE:
            problems.append(Problem(UNKNOWN_FIELD, key))
            continue
        if counts[key] > 1 and key not in reported_twice:
            reported_twice.add(key)
            problems.append(Problem(MAPPED_TWICE, key))
        allowed = allowed_sources(key, template_codes)
        if source not in allowed:
            problems.append(Problem(SOURCE_NOT_ALLOWED, key))
        if fallback:
            if fallback == source:
                problems.append(Problem(FALLBACK_IS_SOURCE, key))
            elif fallback not in allowed:
                problems.append(Problem(FALLBACK_NOT_ALLOWED, key))
    return problems


def choose(values, rows) -> dict[str, str]:
    """Catalogue key -> the value its row takes: the source's, or else the fallback's.

    `values` maps `(key, document_code)` to the value read from that document.
    A key with no row, or whose documents hold no value, is left out.
    """
    chosen: dict[str, str] = {}
    for key, source, fallback in rows:
        value = values.get((key, source))
        if not value and fallback:
            value = values.get((key, fallback))
        if value:
            chosen[key] = value
    return chosen


def default_rows(template_codes) -> list[tuple[str, str, str | None]]:
    """A row for every key these documents can supply: the first source, then the second."""
    rows = []
    for entry in ENTRIES:
        allowed = allowed_sources(entry.key, template_codes)
        if allowed:
            rows.append((entry.key, allowed[0], allowed[1] if len(allowed) > 1 else None))
    return rows
