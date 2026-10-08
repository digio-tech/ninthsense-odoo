import json
import unittest
from pathlib import Path

from core import catalogue
from core.extraction import DocInput, extract
from core.limits import DEFAULT_LIMITS, Limits

FIXTURES = Path(__file__).resolve().parent / "fixtures"
#: Fixture file stem -> the request line code it stands for.
FIXTURE_CODES = {
    "aadhaar_front": "aadhaar_front",
    "aadhaar_back": "aadhaar_back",
    "pan_card": "pan_card",
    "cancelled_cheque": "cancelled_cheque",
    "degree_certificate": "graduation_certificate",
}
DROPPED_KEYS = {"applicant_name", "designation", "date_of_joining", "department", "ctc"}


def _fixture_documents(stems=FIXTURE_CODES):
    documents = []
    for stem in stems:
        data = json.loads((FIXTURES / f"{stem}.json").read_text())
        documents.append(DocInput(FIXTURE_CODES[stem], data["extracted"]))
    return documents


def _by_key(values):
    """Each key's value from its first source document."""
    first = {}
    for value in values:
        first.setdefault(value.field_key, value)
    return first


class TestCatalogue(unittest.TestCase):
    def test_keeps_exactly_the_mapped_keys(self):
        self.assertEqual(
            [entry.key for entry in catalogue.ENTRIES],
            [
                "legal_name",
                "sex",
                "date_of_birth",
                "cell_number",
                "personal_email",
                "current_address",
                "permanent_address",
                "education.institution",
                "education.degree",
                "education.year",
                "education.percentage",
                "external_work_history.employer",
                "external_work_history.designation",
                "external_work_history.total_experience",
                "bank_name",
                "bank_ac_no",
                "ifsc_code",
                "micr_code",
                "pan_number",
                "aadhaar_number",
                "provident_fund_account",
                "passport_number",
                "date_of_issue",
                "valid_upto",
                "place_of_issue",
            ],
        )

    def test_keys_for_letters_and_offers_are_gone(self):
        self.assertFalse(DROPPED_KEYS & set(catalogue.CATALOGUE))
        for entry in catalogue.ENTRIES:
            self.assertFalse((entry.target or "").startswith(("letters.", "display.")))

    def test_sources_use_only_installed_document_codes(self):
        installed = {
            "aadhaar_front",
            "aadhaar_back",
            "pan_card",
            "driving_license",
            "passport",
            "passport_photo",
            "graduation_certificate",
            "masters_certificate",
            "resume",
            "offer_letter",
            "experience_letter",
            "latest_pay_slip",
            "bank_statement",
            "cancelled_cheque",
        }
        for entry in catalogue.ENTRIES:
            for code, _path in entry.sources:
                self.assertIn(code, installed, msg=entry.key)

    def test_values_that_are_only_shown_have_no_target(self):
        shown = {entry.key for entry in catalogue.ENTRIES if entry.target is None}
        self.assertEqual(
            shown,
            {
                "permanent_address",
                "micr_code",
                "pan_number",
                "provident_fund_account",
                "date_of_issue",
                "place_of_issue",
            },
        )

    def test_no_label_repeats_its_section(self):
        for entry in catalogue.ENTRIES:
            self.assertFalse(entry.label.startswith(f"{entry.section}:"), msg=entry.key)
            self.assertNotEqual(entry.section, "Employee Information", msg=entry.key)

    def test_education_and_employment_have_sections_of_their_own(self):
        sections = {entry.key: entry.section for entry in catalogue.ENTRIES}
        self.assertEqual(sections["education.institution"], "Education")
        self.assertEqual(sections["external_work_history.employer"], "Employment")


class TestExtractFixtures(unittest.TestCase):
    def test_one_value_per_key_and_document_in_catalogue_order(self):
        values = extract(_fixture_documents(), DEFAULT_LIMITS)
        pairs = [(value.field_key, value.source_code) for value in values]
        self.assertEqual(len(pairs), len(set(pairs)))
        order = [entry.key for entry in catalogue.ENTRIES]
        keys = [key for key, _code in pairs]
        self.assertEqual(keys, sorted(keys, key=order.index))
        self.assertEqual(
            {(value.field_key, value.source_code): value.value for value in values},
            {
                ("legal_name", "aadhaar_front"): "Priya Raghavan",
                ("legal_name", "pan_card"): "Priya Raghavan",
                ("sex", "aadhaar_front"): "female",
                ("date_of_birth", "aadhaar_front"): "1997-11-09",
                ("date_of_birth", "pan_card"): "1997-11-09",
                ("current_address", "aadhaar_back"): (
                    "14 Nandi Durga Road, Benson Town, Bengaluru 560046"
                ),
                ("permanent_address", "aadhaar_back"): (
                    "14 Nandi Durga Road, Benson Town, Bengaluru 560046"
                ),
                ("education.institution", "graduation_certificate"): "RV College of Engineering",
                ("education.degree", "graduation_certificate"): "B.E. Information Science",
                ("education.year", "graduation_certificate"): "2019",
                ("bank_name", "cancelled_cheque"): "HDFC Bank",
                ("bank_ac_no", "cancelled_cheque"): "50100247731902",
                ("ifsc_code", "cancelled_cheque"): "HDFC0000123",
                ("pan_number", "pan_card"): "ABCPR1234F",
                ("aadhaar_number", "aadhaar_front"): "XXXX XXXX 0123",
            },
        )

    def test_each_value_names_the_document_it_was_read_from(self):
        values = _by_key(extract(_fixture_documents(), DEFAULT_LIMITS))
        self.assertEqual(values["legal_name"].source_code, "aadhaar_front")
        self.assertEqual(values["current_address"].source_code, "aadhaar_back")
        self.assertEqual(values["pan_number"].source_code, "pan_card")
        self.assertEqual(values["education.year"].source_code, "graduation_certificate")
        self.assertEqual(values["bank_name"].label, "Bank Name")

    def test_the_aadhaar_value_is_masked_wherever_it_is_read(self):
        values = extract(_fixture_documents(), DEFAULT_LIMITS)
        aadhaar = _by_key(values)["aadhaar_number"]
        self.assertEqual(aadhaar.value, "XXXX XXXX 0123")
        self.assertNotIn("2345", " ".join(value.value for value in values))

    def test_an_aadhaar_that_is_not_twelve_digits_is_unreadable(self):
        for raw in ("2345 6789", "ABCD EFGH IJKL", 12345):
            with self.subTest(raw=raw):
                values = extract(
                    [DocInput("aadhaar_front", {"aadhaar_number": raw})], DEFAULT_LIMITS
                )
                self.assertEqual(_by_key(values)["aadhaar_number"].value, "unreadable")

    def test_a_numeric_aadhaar_is_masked_not_unreadable(self):
        values = extract(
            [DocInput("aadhaar_front", {"aadhaar_number": 234567890123})], DEFAULT_LIMITS
        )
        self.assertEqual(_by_key(values)["aadhaar_number"].value, "XXXX XXXX 0123")

    def test_unknown_documents_and_fields_yield_nothing(self):
        documents = [DocInput("pan_card", {"father_name": "X", "branch": "Y"})]
        self.assertEqual(extract(documents, DEFAULT_LIMITS), [])
        self.assertEqual(extract([DocInput("pan_card", None)], DEFAULT_LIMITS), [])


class TestEverySource(unittest.TestCase):
    def test_each_source_document_keeps_its_own_value_in_catalogue_order(self):
        documents = [
            DocInput("pan_card", {"name": "From Pan"}),
            DocInput("aadhaar_front", {"name": "From Aadhaar"}),
        ]
        values = [
            (value.source_code, value.value)
            for value in extract(documents, DEFAULT_LIMITS)
            if value.field_key == "legal_name"
        ]
        self.assertEqual(values, [("aadhaar_front", "From Aadhaar"), ("pan_card", "From Pan")])

    def test_an_empty_or_placeholder_value_is_not_kept(self):
        for token in ("", "null", "not visible", "N/A", "-"):
            with self.subTest(token=token):
                documents = [
                    DocInput("aadhaar_front", {"name": token}),
                    DocInput("pan_card", {"name": "Priya Raghavan"}),
                ]
                sources = [
                    value.source_code
                    for value in extract(documents, DEFAULT_LIMITS)
                    if value.field_key == "legal_name"
                ]
                self.assertEqual(sources, ["pan_card"])

    def test_a_value_the_transform_drops_is_not_kept(self):
        documents = [
            DocInput("aadhaar_front", {"name": "14, MG Road, Bengaluru 560001"}),
            DocInput("pan_card", {"name": "Priya Raghavan"}),
        ]
        sources = [
            value.source_code
            for value in extract(documents, DEFAULT_LIMITS)
            if value.field_key == "legal_name"
        ]
        self.assertEqual(sources, ["pan_card"])

    def test_a_source_not_among_the_documents_is_skipped(self):
        values = _by_key(extract([DocInput("resume", {"full_name": "Priya R"})], DEFAULT_LIMITS))
        self.assertEqual(values["legal_name"].source_code, "resume")

    def test_two_documents_with_one_code_keep_the_first_readable_value(self):
        documents = [
            DocInput("resume", {"phone": "-"}),
            DocInput("resume", {"phone": "+91 98450 12345"}),
            DocInput("resume", {"phone": "+91 98450 99999"}),
        ]
        values = [
            value.value
            for value in extract(documents, DEFAULT_LIMITS)
            if value.field_key == "cell_number"
        ]
        self.assertEqual(values, ["+91 98450 12345"])


class TestDroppedKeys(unittest.TestCase):
    def test_nothing_is_produced_for_keys_whose_target_was_dropped(self):
        documents = [
            DocInput("aadhaar_front", {"name": "Priya Raghavan"}),
            DocInput("pan_card", {"name": "Priya Raghavan"}),
            DocInput("resume", {"full_name": "Priya Raghavan"}),
            DocInput(
                "offer_letter",
                {
                    "employee_name": "Priya Raghavan",
                    "designation": "Engineer",
                    "date_of_joining": "2026-10-01",
                    "department": "R&D",
                    "salary": "1200000",
                },
            ),
            DocInput("latest_pay_slip", {"designation": "Engineer", "department": "R&D"}),
        ]
        keys = {value.field_key for value in extract(documents, DEFAULT_LIMITS)}
        self.assertFalse(keys & DROPPED_KEYS)
        self.assertNotIn(
            "offer_letter", {v.source_code for v in extract(documents, DEFAULT_LIMITS)}
        )


class TestTransforms(unittest.TestCase):
    def _one(self, code, extracted, key):
        return _by_key(extract([DocInput(code, extracted)], DEFAULT_LIMITS)).get(key)

    def test_name_is_title_cased_when_printed_in_capitals(self):
        value = self._one("aadhaar_front", {"name": "PRIYA SURESH RAGHAVAN"}, "legal_name")
        self.assertEqual(value.value, "Priya Suresh Raghavan")

    def test_gender_maps_to_a_selection_key_or_nothing(self):
        self.assertEqual(self._one("aadhaar_front", {"gender": "Male"}, "sex").value, "male")
        self.assertIsNone(self._one("aadhaar_front", {"gender": "Other"}, "sex"))

    def test_dates_accept_iso_and_day_first_and_drop_the_rest(self):
        dob = "date_of_birth"
        self.assertEqual(self._one("aadhaar_front", {dob: "09/11/1997"}, dob).value, "1997-11-09")
        self.assertIsNone(self._one("aadhaar_front", {dob: "9th November 1997"}, dob))

    def test_an_address_block_is_composed(self):
        block = {"line1": "14 Road", "city": "Bengaluru", "state": "Karnataka", "pin": "560046"}
        value = self._one("aadhaar_back", {"address": block}, "current_address")
        self.assertEqual(value.value, "14 Road, Bengaluru, Karnataka, 560046")

    def test_pan_is_upper_cased(self):
        self.assertEqual(
            self._one("pan_card", {"pan_number": "abcpr1234f"}, "pan_number").value, "ABCPR1234F"
        )

    def test_values_are_cut_to_the_configured_limit(self):
        documents = [DocInput("bank_statement", {"address": "x" * 1500})]
        values = _by_key(extract(documents, Limits()))
        self.assertEqual(len(values["current_address"].value), 1024)


if __name__ == "__main__":
    unittest.main()
