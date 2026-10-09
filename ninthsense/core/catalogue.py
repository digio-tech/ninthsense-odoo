"""Every value 9thSense can read for an onboarding request, and where it is read from.

An entry names a catalogue key, the label shown for it, the section it is
listed under, the transform applied to the raw value, and the ordered
`(document_code, path)` pairs it may be read from. A template's field mapping
picks which of those documents the value is taken from.

`target` says where the value goes: an `hr.employee` field name, `bank.<attr>`
for the bank account created on save, `resume.<kind>.<attr>` for a resume line
created on save, or `None` for a value that is only shown as parsed data.
"""

from dataclasses import dataclass

_PERSONAL = "Personal Information"
_ADDRESS = "Address Verification"
_EDUCATION = "Education"
_EMPLOYMENT = "Employment"
_BANKING = "Banking"
_STATUTORY = "Statutory"


@dataclass(frozen=True)
class Entry:
    key: str
    label: str
    section: str
    target: str | None
    transform: str | None
    sources: tuple[tuple[str, str], ...]


ENTRIES = (
    Entry(
        "legal_name",
        "Legal Name",
        _PERSONAL,
        "legal_name",
        "Name Part",
        (
            ("aadhaar_front", "name"),
            ("pan_card", "name"),
            ("passport", "given_name"),
            ("resume", "full_name"),
            ("latest_pay_slip", "employee_name"),
        ),
    ),
    Entry("sex", "Sex", _PERSONAL, "sex", "Gender", (("aadhaar_front", "gender"),)),
    Entry(
        "date_of_birth",
        "Date of Birth",
        _PERSONAL,
        "birthday",
        "Date",
        (
            ("aadhaar_front", "date_of_birth"),
            ("pan_card", "date_of_birth"),
            ("passport", "date_of_birth"),
            ("resume", "date_of_birth"),
        ),
    ),
    Entry(
        "cell_number",
        "Mobile",
        _PERSONAL,
        "private_phone",
        None,
        (("resume", "phone"), ("bank_statement", "mobile_number")),
    ),
    Entry(
        "personal_email",
        "Personal Email",
        _PERSONAL,
        "private_email",
        None,
        (("resume", "email"), ("bank_statement", "email")),
    ),
    Entry(
        "current_address",
        "Current Address",
        _ADDRESS,
        "private_address",
        "Compose Address",
        (
            ("aadhaar_back", "address"),
            ("aadhaar_front", "address"),
            ("resume", "current_address"),
            ("bank_statement", "address"),
        ),
    ),
    Entry(
        "permanent_address",
        "Permanent Address",
        _ADDRESS,
        None,
        "Compose Address",
        (
            ("aadhaar_back", "address"),
            ("aadhaar_front", "address"),
            ("resume", "current_address"),
            ("bank_statement", "address"),
        ),
    ),
    Entry(
        "education.institution",
        "Institution",
        _EDUCATION,
        "resume.education.institution",
        None,
        (
            ("graduation_certificate", "institution"),
            ("resume", "highest_qualification_institution"),
        ),
    ),
    Entry(
        "education.degree",
        "Degree",
        _EDUCATION,
        "resume.education.degree",
        None,
        (("graduation_certificate", "degree"), ("resume", "highest_qualification")),
    ),
    Entry(
        "education.year",
        "Year of Passing",
        _EDUCATION,
        "resume.education.year",
        "Year",
        (
            ("graduation_certificate", "year_of_passing"),
            ("resume", "highest_qualification_year"),
        ),
    ),
    Entry(
        "education.percentage",
        "Percentage",
        _EDUCATION,
        "resume.education.percentage",
        None,
        (("graduation_certificate", "percentage"),),
    ),
    Entry(
        "external_work_history.employer",
        "Previous Employer",
        _EMPLOYMENT,
        "resume.experience.employer",
        None,
        (("resume", "current_employer"), ("latest_pay_slip", "employer_name")),
    ),
    Entry(
        "external_work_history.designation",
        "Previous Designation",
        _EMPLOYMENT,
        "resume.experience.designation",
        None,
        (("resume", "current_designation"), ("latest_pay_slip", "designation")),
    ),
    Entry(
        "external_work_history.total_experience",
        "Total Experience",
        _EMPLOYMENT,
        "resume.experience.total_experience",
        None,
        (("resume", "total_experience_years"),),
    ),
    Entry(
        "bank_name",
        "Bank Name",
        _BANKING,
        "bank.bank_name",
        None,
        (
            ("cancelled_cheque", "bank_name"),
            ("bank_statement", "bank_name"),
            ("latest_pay_slip", "bank_name"),
        ),
    ),
    Entry(
        "bank_ac_no",
        "Bank Account Number",
        _BANKING,
        "bank.account_number",
        None,
        (
            ("cancelled_cheque", "account_number"),
            ("bank_statement", "account_number"),
            ("latest_pay_slip", "bank_account"),
        ),
    ),
    Entry(
        "ifsc_code",
        "IFSC Code",
        _BANKING,
        "bank.ifsc",
        None,
        (("cancelled_cheque", "ifsc_code"), ("bank_statement", "ifsc_code")),
    ),
    Entry("micr_code", "MICR Code", _BANKING, None, None, (("cancelled_cheque", "micr_code"),)),
    Entry(
        "pan_number",
        "PAN",
        _STATUTORY,
        None,
        "Upper",
        (("pan_card", "pan_number"), ("latest_pay_slip", "pan_number")),
    ),
    Entry(
        "aadhaar_number",
        "Aadhaar Number",
        _STATUTORY,
        "identification_id",
        None,
        (("aadhaar_front", "aadhaar_number"),),
    ),
    Entry(
        "provident_fund_account",
        "PF Account",
        _STATUTORY,
        None,
        None,
        (("latest_pay_slip", "pf_number"),),
    ),
    Entry(
        "passport_number",
        "Passport Number",
        _STATUTORY,
        "passport_id",
        None,
        (("passport", "passport_number"),),
    ),
    Entry(
        "date_of_issue",
        "Passport Issue Date",
        _STATUTORY,
        None,
        "Date",
        (("passport", "date_of_issue"),),
    ),
    Entry(
        "valid_upto",
        "Passport Valid Until",
        _STATUTORY,
        "passport_expiration_date",
        "Date",
        (("passport", "valid_upto"),),
    ),
    Entry(
        "place_of_issue",
        "Passport Place of Issue",
        _STATUTORY,
        None,
        None,
        (("passport", "place_of_issue"),),
    ),
)

CATALOGUE: dict[str, Entry] = {entry.key: entry for entry in ENTRIES}
