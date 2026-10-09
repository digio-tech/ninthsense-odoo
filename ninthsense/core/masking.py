"""Aadhaar number masking: only the last four digits ever leave this package."""

import re

_SEPARATORS = re.compile(r"[\s-]")


def mask_aadhaar(value) -> str:
    """A raw Aadhaar value, masked.

    Twelve digits, however they are grouped with spaces or hyphens, mask to
    `"XXXX XXXX dddd"`. Anything else -- a shorter or longer number, letters,
    a non-string -- cannot be trusted to be an Aadhaar number at all, so it is
    replaced outright rather than partially shown.
    """
    if not isinstance(value, str):
        return "unreadable"
    digits = _SEPARATORS.sub("", value)
    if len(digits) == 12 and digits.isdigit():
        return f"XXXX XXXX {digits[-4:]}"
    return "unreadable"


#: Twelve digits, separated by any run of spaces, dots, hyphens or slashes,
#: not part of a longer number.
AADHAAR_RUN = re.compile(r"(?<!\d)\d(?:[\s./-]*\d){11}(?!\d)")
_NON_DIGITS = re.compile(r"\D")
#: India's country code before a mobile number: `+91`, or `91` set apart by a
#: separator. A bare `91...` run could be an Aadhaar number, so it is not one.
_INDIAN_PREFIX = re.compile(r"^\s*(?:\+\s*91[\s./-]*|91[\s./-]+)(?=[6-9])")


def mask_runs(text: str) -> str:
    """`text` with every Aadhaar-shaped run of digits reduced to its last four."""
    return AADHAAR_RUN.sub(lambda match: mask_aadhaar(_NON_DIGITS.sub("", match.group(0))), text)


def mask_tree(value):
    """A copy of a parsed JSON value with every Aadhaar-shaped run masked.

    Strings, keys and numbers are all scanned, since a free-form result can
    carry the number in any of them.
    """
    if isinstance(value, dict):
        return {mask_runs(key): mask_tree(item) for key, item in value.items()}
    if isinstance(value, list):
        return [mask_tree(item) for item in value]
    if isinstance(value, str):
        return mask_runs(value)
    if isinstance(value, int | float) and not isinstance(value, bool):
        text = str(value)
        return mask_runs(text) if AADHAAR_RUN.search(text) else value
    return value


def national_phone(value: str) -> str:
    """An Indian mobile number without its `+91` or `91 ` prefix.

    With the prefix, a ten-digit mobile is twelve digits long, the shape of
    an Aadhaar number. Anything else is returned unchanged, to be masked.
    """
    digits = _NON_DIGITS.sub("", value)
    if len(digits) != 12 or not digits.startswith("91"):
        return value
    national = _INDIAN_PREFIX.sub("", value, count=1)
    return national if len(_NON_DIGITS.sub("", national)) == 10 else value
