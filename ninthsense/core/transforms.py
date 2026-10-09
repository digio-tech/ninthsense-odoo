"""Named shaping applied to a raw extracted value before it is proposed.

Every transform is total: it either returns a usable value or `None`, never
raises. A rejected value is reported by the caller as the value not having
survived its transform, using one fixed note -- these functions do not invent
their own wording.
"""

import datetime
import re

#: Placeholders the provider sends in place of a value.
NULLISH = frozenset({"", "null", "none", "n/a", "na", "not visible", "not available", "-"})

#: Odoo's `sex` field only ever holds one of these two.
GENDER_CODES = {"m": "male", "male": "male", "f": "female", "female": "female"}

_YEAR = re.compile(r"\b(19|20)\d{2}\b")
_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_DMY_DATE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")


def clean_value(value):
    """`None` for one of the provider's placeholder tokens, the value otherwise."""
    if isinstance(value, str) and value.strip().lower() in NULLISH:
        return None
    return value


def _looks_like_address(value) -> bool:
    """An Aadhaar back side sometimes hands its address back as the name."""
    return isinstance(value, str) and (
        sum(c.isdigit() for c in value) >= 3 or value.count(",") >= 2
    )


def name_part(raw):
    """A person's full name, cleaned up and joined with single spaces.

    9thSense sends a single string. All-caps names (PAN prints them that way)
    are title-cased; a value that looks like an address rather than a name is
    dropped.
    """
    raw = clean_value(raw)
    if not isinstance(raw, str) or not raw.strip() or _looks_like_address(raw):
        return None
    parts = [part for part in raw.split() if part]
    if not parts:
        return None
    if raw.isupper():
        parts = [part.title() for part in parts]
    return " ".join(parts)


def compose_address(block):
    """A single address line from either a string or a block of parts."""
    block = clean_value(block)
    if isinstance(block, str):
        return block.strip() or None
    if not isinstance(block, dict):
        return None
    full = clean_value(block.get("full"))
    if full:
        return str(full).strip() or None
    parts = [
        clean_value(block.get("line1")),
        clean_value(block.get("line2")),
        clean_value(block.get("city")),
        clean_value(block.get("state")),
        clean_value(block.get("pincode") or block.get("pin") or block.get("zip")),
    ]
    joined = ", ".join(str(part).strip() for part in parts if part and str(part).strip())
    return joined or None


def gender(raw):
    """`"male"` or `"female"`, or `None` for anything else."""
    raw = clean_value(raw)
    if not isinstance(raw, str) or not raw.strip():
        return None
    return GENDER_CODES.get(raw.strip().lower())


def year(raw):
    """The year out of a date-ish value: `"May 2017"` -> `"2017"`."""
    raw = clean_value(raw)
    if isinstance(raw, int) and 1900 <= raw <= 2099:
        return str(raw)
    match = _YEAR.search(str(raw or ""))
    return match.group(0) if match else None


def upper(raw):
    raw = clean_value(raw)
    if raw is None:
        return None
    return str(raw).strip().upper() or None


def to_date(raw):
    """The date as ISO `YYYY-MM-DD`, accepting ISO or `dd/mm/yyyy` input."""
    raw = clean_value(raw)
    if raw is None:
        return None
    text = str(raw).strip()
    match = _ISO_DATE.match(text)
    if match:
        year_s, month_s, day_s = match.groups()
    else:
        match = _DMY_DATE.match(text)
        if not match:
            return None
        day_s, month_s, year_s = match.groups()
    try:
        parsed = datetime.date(int(year_s), int(month_s), int(day_s))
    except ValueError:
        return None
    return parsed.isoformat()


TRANSFORMS = {
    "Name Part": name_part,
    "Compose Address": compose_address,
    "Gender": gender,
    "Year": year,
    "Date": to_date,
    "Upper": upper,
}


def apply_transform(value, transform: str | None):
    """The value after its named transform. An unknown or blank name is a no-op."""
    if value is None:
        return None
    handler = TRANSFORMS.get((transform or "").strip())
    if not handler:
        return value
    return handler(value)
