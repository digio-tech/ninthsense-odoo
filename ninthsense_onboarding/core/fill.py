"""Decide which empty employee fields the parsed values fill, and report every decision.

`build` takes the values the new employee form starts with, the parsed values
the template's mapping chose (one per catalogue key), a description of each
target field, and the country and state records already looked up by name. It
returns the values to fill, one report row per value used, and the bank account
and resume lines to create once the employee is saved.

A field that already holds a value is never changed. A value that does not fit
its field (a bad date, too long, not one of the choices, no single matching
record) is reported as invalid and not used. Yes/no fields are never filled.

Reasons are short codes. The caller turns them into translated text.
"""

import datetime
import re
from dataclasses import dataclass

from .catalogue import CATALOGUE, ENTRIES
from .transforms import clean_value, to_date

FILLED = "filled"
SKIPPED_DIFFERENT = "skipped_different"
SKIPPED_INVALID = "skipped_invalid"

NEVER_FILLED = "never_filled"
UNKNOWN_FIELD = "unknown_field"
UNSUPPORTED_TYPE = "unsupported_type"
INVALID_DATE = "invalid_date"
NOT_IN_PAST = "not_in_past"
TOO_LONG = "too_long"
INVALID_EMAIL = "invalid_email"
NOT_A_CHOICE = "not_a_choice"
NO_MATCH = "no_match"
SEVERAL_MATCHES = "several_matches"
NO_COUNTRY = "no_country"
AADHAAR_UNREADABLE = "aadhaar_unreadable"
NO_ACCOUNT_NUMBER = "no_account_number"
INVALID_IFSC = "invalid_ifsc"
INCOMPLETE_EDUCATION = "incomplete_education"
INCOMPLETE_EXPERIENCE = "incomplete_experience"

#: The catalogue's symbolic target for the current address, split into parts.
ADDRESS_TARGET = "private_address"
ADDRESS_KEY = "current_address"
STREET, CITY, ZIP, STATE, COUNTRY = (
    "private_street",
    "private_city",
    "private_zip",
    "private_state_id",
    "private_country_id",
)
ADDRESS_PART_LABELS = {
    STREET: "Street",
    CITY: "City",
    ZIP: "PIN",
    STATE: "State",
    COUNTRY: "Country",
}

EDUCATION_LABEL = "Education"
EXPERIENCE_LABEL = "Previous Employment"

_EMAIL_TARGETS = frozenset({"private_email"})
_PAST_DATE_TARGETS = frozenset({"birthday"})
_AADHAAR_KEY = "aadhaar_number"
_MASKED_AADHAAR = re.compile(r"^XXXX XXXX \d{4}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_IFSC = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
_PIN = re.compile(r"(\d{6})\s*$")

#: The 28 states and 8 union territories, longest name first so a search for
#: "Uttar Pradesh" is not pre-empted by a shorter, unrelated match.
INDIAN_STATES: tuple[str, ...] = tuple(
    sorted(
        (
            "Andhra Pradesh",
            "Arunachal Pradesh",
            "Assam",
            "Bihar",
            "Chhattisgarh",
            "Goa",
            "Gujarat",
            "Haryana",
            "Himachal Pradesh",
            "Jharkhand",
            "Karnataka",
            "Kerala",
            "Madhya Pradesh",
            "Maharashtra",
            "Manipur",
            "Meghalaya",
            "Mizoram",
            "Nagaland",
            "Odisha",
            "Punjab",
            "Rajasthan",
            "Sikkim",
            "Tamil Nadu",
            "Telangana",
            "Tripura",
            "Uttar Pradesh",
            "Uttarakhand",
            "West Bengal",
            "Andaman and Nicobar Islands",
            "Chandigarh",
            "Dadra and Nagar Haveli and Daman and Diu",
            "Delhi",
            "Jammu and Kashmir",
            "Ladakh",
            "Lakshadweep",
            "Puducherry",
        ),
        key=len,
        reverse=True,
    )
)
INDIA = "India"


@dataclass(frozen=True)
class ReportRow:
    outcome: str
    label: str
    value: str
    current_value: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class FillResult:
    fill: dict
    report: list[ReportRow]
    bank: dict | None
    resume_lines: list[dict]


def employee_targets() -> tuple[str, ...]:
    """Every employee field the catalogue can fill, the address split into its parts."""
    names: list[str] = []
    for entry in ENTRIES:
        target = entry.target
        if not target or target.startswith(("bank.", "resume.")):
            continue
        if target == ADDRESS_TARGET:
            names.extend(ADDRESS_PART_LABELS)
        else:
            names.append(target)
    return tuple(dict.fromkeys(names))


def split_address(composed: str) -> dict[str, str]:
    """The street, city, PIN, state name and country name found in one address line.

    The PIN is a trailing six-digit number. The state is the first Indian state
    or union territory named. A PIN or a state means the country is India. Of
    what is left, the last comma-separated part is the city and the rest the
    street.
    """
    text = composed.strip()
    result: dict[str, str] = {}

    pin_match = _PIN.search(text)
    if pin_match:
        result[ZIP] = pin_match.group(1)
        text = text[: pin_match.start()].rstrip(" ,")

    for state in INDIAN_STATES:
        pattern = re.compile(r"(?<!\w)" + re.escape(state) + r"(?!\w)", re.IGNORECASE)
        match = pattern.search(text)
        if match:
            result[STATE] = state
            text = text[: match.start()] + text[match.end() :]
            text = re.sub(r",\s*,", ",", text).strip(" ,")
            break

    if ZIP in result or STATE in result:
        result[COUNTRY] = INDIA

    parts = [part.strip() for part in text.split(",") if part.strip()]
    if parts:
        result[CITY] = parts[-1]
        street = ", ".join(parts[:-1])
        if street:
            result[STREET] = street
    elif text:
        result[STREET] = text
    return result


def address_names(values: dict) -> tuple[str | None, str | None]:
    """`(country name, state name)` the current address names, for the caller to look up."""
    raw = _text(values.get(ADDRESS_KEY))
    if not raw:
        return None, None
    parts = split_address(raw)
    return parts.get(COUNTRY), parts.get(STATE)


def _text(value) -> str | None:
    value = clean_value(value)
    if value is None or value is False:
        return None
    text = str(value).strip()
    return text or None


def _is_empty(value) -> bool:
    return value is None or value is False or value == "" or value == [] or value == ()


def _record_id(value):
    if isinstance(value, tuple | list) and value:
        return value[0]
    return value


def _normalised(value):
    if _is_empty(value):
        return ""
    if isinstance(value, tuple | list):
        return _record_id(value)
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, int | float):
        return value
    return " ".join(str(value).split()).casefold()


def _shown(value) -> str:
    if isinstance(value, tuple | list) and len(value) > 1:
        return str(value[1])
    if isinstance(value, datetime.date):
        return value.isoformat()
    return str(value)


def _selection_keys(info) -> dict[str, str]:
    """Lower-cased key or label -> key, for every choice of a selection field."""
    choices: dict[str, str] = {}
    for item in info.get("selection") or ():
        if isinstance(item, tuple | list):
            key, label = item[0], item[1]
            choices[str(label).casefold()] = key
        else:
            key = item
        choices[str(key).casefold()] = key
    return choices


class _Builder:
    def __init__(self, start, fields_info, matches, today):
        self.start = start
        self.fields_info = fields_info
        self.countries = (matches or {}).get("country") or {}
        self.states = (matches or {}).get("state") or {}
        self.today = today
        self.fill: dict = {}
        self.report: list[ReportRow] = []

    def invalid(self, label, shown, reason):
        self.report.append(ReportRow(SKIPPED_INVALID, label, shown, reason=reason))

    def place(self, target, label, shown, converted):
        """Fill `target` when it is empty, report it as different, or leave it out as equal."""
        current = self.start.get(target)
        if _is_empty(current):
            self.fill[target] = converted
            self.report.append(ReportRow(FILLED, label, shown))
        elif _normalised(current) != _normalised(converted):
            self.report.append(
                ReportRow(SKIPPED_DIFFERENT, label, shown, current_value=_shown(current))
            )

    def field(self, key, target, label, raw):
        info = self.fields_info.get(target)
        if info is None:
            self.invalid(label, raw, UNKNOWN_FIELD)
            return
        converted, reason = self.convert(key, target, info, raw)
        if reason:
            self.invalid(label, raw, reason)
            return
        self.place(target, label, raw, converted)

    def convert(self, key, target, info, raw):
        """`(value, None)` ready for the field, or `(None, reason)` when it does not fit."""
        kind = info.get("type")
        if kind == "boolean":
            return None, NEVER_FILLED
        if kind in ("char", "text"):
            if key == _AADHAAR_KEY and not _MASKED_AADHAAR.match(raw):
                return None, AADHAAR_UNREADABLE
            if target in _EMAIL_TARGETS and not _EMAIL.match(raw):
                return None, INVALID_EMAIL
            size = info.get("size")
            if size and len(raw) > size:
                return None, TOO_LONG
            return raw, None
        if kind == "date":
            iso = to_date(raw)
            if iso is None:
                return None, INVALID_DATE
            if target in _PAST_DATE_TARGETS and datetime.date.fromisoformat(iso) >= self.today:
                return None, NOT_IN_PAST
            return iso, None
        if kind == "selection":
            choice = _selection_keys(info).get(raw.casefold())
            if choice is None:
                return None, NOT_A_CHOICE
            return choice, None
        return None, UNSUPPORTED_TYPE

    def record(self, target, label, name, ids):
        if self.fields_info.get(target) is None:
            self.invalid(label, name, UNKNOWN_FIELD)
            return
        if not ids:
            self.invalid(label, name, NO_MATCH)
        elif len(ids) > 1:
            self.invalid(label, name, SEVERAL_MATCHES)
        else:
            self.place(target, label, name, ids[0])

    def address(self, label, raw):
        parts = split_address(raw)

        def part_label(target):
            return f"{label} ({ADDRESS_PART_LABELS[target]})"

        for target in (STREET, CITY, ZIP):
            if parts.get(target):
                self.field(ADDRESS_KEY, target, part_label(target), parts[target])

        country_name = parts.get(COUNTRY)
        if country_name:
            self.record(
                COUNTRY, part_label(COUNTRY), country_name, self.countries.get(country_name, [])
            )

        state_name = parts.get(STATE)
        if state_name:
            country_id = self.fill.get(COUNTRY) or _record_id(self.start.get(COUNTRY))
            if _is_empty(country_id):
                self.invalid(part_label(STATE), state_name, NO_COUNTRY)
            else:
                self.record(
                    STATE,
                    part_label(STATE),
                    state_name,
                    self.states.get((country_id, state_name), []),
                )


def _bank(values, report) -> dict | None:
    number = _text(values.get("bank_ac_no"))
    bank_name = _text(values.get("bank_name"))
    ifsc = _text(values.get("ifsc_code"))
    if not number:
        for key, raw in (("bank_name", bank_name), ("ifsc_code", ifsc)):
            if raw:
                report.append(
                    ReportRow(SKIPPED_INVALID, CATALOGUE[key].label, raw, reason=NO_ACCOUNT_NUMBER)
                )
        return None
    bank = {"account_number": number}
    if bank_name:
        bank["bank_name"] = bank_name
    if ifsc:
        code = ifsc.replace(" ", "").upper()
        if _IFSC.match(code):
            bank["clearing_number"] = code
        else:
            report.append(
                ReportRow(SKIPPED_INVALID, CATALOGUE["ifsc_code"].label, ifsc, reason=INVALID_IFSC)
            )
    return bank


def _education_line(values, report) -> dict | None:
    degree = _text(values.get("education.degree"))
    institution = _text(values.get("education.institution"))
    year = _text(values.get("education.year"))
    percentage = _text(values.get("education.percentage"))
    if not (degree or institution):
        read = [part for part in (year, percentage) if part]
        if read:
            report.append(
                ReportRow(
                    SKIPPED_INVALID,
                    EDUCATION_LABEL,
                    ", ".join(read),
                    reason=INCOMPLETE_EDUCATION,
                )
            )
        return None
    return {
        "line_type": "education",
        "name": ", ".join(part for part in (degree, institution) if part),
        "date_start": f"{year}-01-01" if year and year.isdigit() and len(year) == 4 else None,
        "details": {"percentage": percentage} if percentage else {},
    }


def _experience_line(values, report) -> dict | None:
    employer = _text(values.get("external_work_history.employer"))
    designation = _text(values.get("external_work_history.designation"))
    total = _text(values.get("external_work_history.total_experience"))
    if not employer:
        read = [part for part in (designation, total) if part]
        if read:
            report.append(
                ReportRow(
                    SKIPPED_INVALID,
                    EXPERIENCE_LABEL,
                    ", ".join(read),
                    reason=INCOMPLETE_EXPERIENCE,
                )
            )
        return None
    details = {}
    if designation:
        details["designation"] = designation
    if total:
        details["total_experience"] = total
    return {"line_type": "experience", "name": employer, "date_start": None, "details": details}


def build(
    start: dict,
    values: dict,
    fields_info: dict,
    matches: dict,
    today: datetime.date | None = None,
) -> FillResult:
    """The fill for a new employee form, its report, and what to create on save.

    `start` maps a field name to the value the form starts with. A many2one
    value may be an id or an `(id, name)` pair. `values` maps a catalogue key to
    the parsed value chosen for it; a key left out is not filled. `fields_info`
    maps a field name to its `type`, `size` and `selection`. `matches` holds
    the record ids found by name:
    `{"country": {name: [ids]}, "state": {(country_id, name): [ids]}}`.
    """
    builder = _Builder(start, fields_info, matches, today or datetime.date.today())
    for entry in ENTRIES:
        target = entry.target
        if not target or target.startswith(("bank.", "resume.")):
            continue
        raw = _text(values.get(entry.key))
        if raw is None:
            continue
        if target == ADDRESS_TARGET:
            builder.address(entry.label, raw)
        else:
            builder.field(entry.key, target, entry.label, raw)

    report = builder.report
    bank = _bank(values, report)
    resume_lines = [
        line
        for line in (_education_line(values, report), _experience_line(values, report))
        if line is not None
    ]
    return FillResult(fill=builder.fill, report=report, bank=bank, resume_lines=resume_lines)
