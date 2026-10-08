import datetime
import unittest

from core import fill

TODAY = datetime.date(2026, 10, 7)
INDIA_ID = 104
US_ID = 233
KARNATAKA_ID = 588

FIELDS = {
    "legal_name": {"type": "char"},
    "sex": {"type": "selection", "selection": [["male", "Male"], ["female", "Female"]]},
    "birthday": {"type": "date"},
    "private_phone": {"type": "char"},
    "private_email": {"type": "char"},
    "private_street": {"type": "char"},
    "private_city": {"type": "char"},
    "private_zip": {"type": "char", "size": 6},
    "private_state_id": {"type": "many2one"},
    "private_country_id": {"type": "many2one"},
    "identification_id": {"type": "char"},
    "passport_id": {"type": "char", "size": 8},
    "passport_expiration_date": {"type": "date"},
}
MATCHES = {
    "country": {"India": [INDIA_ID]},
    "state": {(INDIA_ID, "Karnataka"): [KARNATAKA_ID]},
}
ADDRESS = "14 Nandi Durga Road, Benson Town, Bengaluru, Karnataka 560046"


def build(values, start=None, fields_info=FIELDS, matches=MATCHES):
    return fill.build(start or {}, values, fields_info, matches, today=TODAY)


def rows(result, outcome=None):
    return {row.label: row for row in result.report if outcome is None or row.outcome == outcome}


class TestFieldFill(unittest.TestCase):
    def test_empty_target_is_filled_and_reported(self):
        result = build({"personal_email": "priya@example.com"})

        self.assertEqual(result.fill, {"private_email": "priya@example.com"})
        row = rows(result)["Personal Email"]
        self.assertEqual(row.outcome, fill.FILLED)
        self.assertEqual(row.value, "priya@example.com")

    def test_target_with_a_different_value_is_untouched(self):
        result = build({"cell_number": "9845012345"}, start={"private_phone": "+1 555 0100"})

        self.assertEqual(result.fill, {})
        row = rows(result)["Mobile"]
        self.assertEqual(row.outcome, fill.SKIPPED_DIFFERENT)
        self.assertEqual(row.value, "9845012345")
        self.assertEqual(row.current_value, "+1 555 0100")

    def test_same_value_after_normalisation_is_left_out(self):
        result = build(
            {"legal_name": "Priya  Raghavan", "date_of_birth": "1997-11-09"},
            start={"legal_name": "priya raghavan", "birthday": datetime.date(1997, 11, 9)},
        )

        self.assertEqual(result.fill, {})
        self.assertEqual(result.report, [])

    def test_boolean_target_is_never_filled(self):
        fields_info = dict(FIELDS, private_email={"type": "boolean"})
        result = build({"personal_email": "priya@example.com"}, fields_info=fields_info)

        self.assertEqual(result.fill, {})
        row = rows(result)["Personal Email"]
        self.assertEqual(row.outcome, fill.SKIPPED_INVALID)
        self.assertEqual(row.reason, fill.NEVER_FILLED)

    def test_invalid_values_are_reported_with_a_reason(self):
        result = build(
            {
                "date_of_birth": "31/02/1997",
                "passport_number": "K1234567890",
                "personal_email": "not an email",
                "valid_upto": "someday",
            }
        )

        self.assertEqual(result.fill, {})
        invalid = rows(result, fill.SKIPPED_INVALID)
        self.assertEqual(invalid["Date of Birth"].reason, fill.INVALID_DATE)
        self.assertEqual(invalid["Passport Number"].reason, fill.TOO_LONG)
        self.assertEqual(invalid["Personal Email"].reason, fill.INVALID_EMAIL)
        self.assertEqual(invalid["Passport Valid Until"].reason, fill.INVALID_DATE)

    def test_birthday_must_be_in_the_past(self):
        result = build({"date_of_birth": "2030-01-01"})

        self.assertEqual(rows(result)["Date of Birth"].reason, fill.NOT_IN_PAST)

    def test_dates_are_filled_as_iso(self):
        result = build({"date_of_birth": "09/11/1997", "valid_upto": "2031-05-01"})

        self.assertEqual(
            result.fill, {"birthday": "1997-11-09", "passport_expiration_date": "2031-05-01"}
        )

    def test_sex_maps_to_a_selection_key(self):
        self.assertEqual(build({"sex": "Male"}).fill, {"sex": "male"})

        result = build({"sex": "X"})
        self.assertEqual(result.fill, {})
        self.assertEqual(rows(result)["Sex"].reason, fill.NOT_A_CHOICE)

    def test_masked_aadhaar_fills_identification(self):
        result = build({"aadhaar_number": "XXXX XXXX 1234"})
        self.assertEqual(result.fill, {"identification_id": "XXXX XXXX 1234"})

        result = build({"aadhaar_number": "unreadable"})
        self.assertEqual(result.fill, {})
        row = rows(result)["Aadhaar Number"]
        self.assertEqual(row.outcome, fill.SKIPPED_INVALID)
        self.assertEqual(row.reason, fill.AADHAAR_UNREADABLE)

    def test_legal_name_differing_from_the_start_is_skipped(self):
        result = build({"legal_name": "Priya R"}, start={"legal_name": "Priya Raghavan"})

        row = rows(result)["Legal Name"]
        self.assertEqual(row.outcome, fill.SKIPPED_DIFFERENT)
        self.assertEqual(row.current_value, "Priya Raghavan")

    def test_no_values_fill_nothing(self):
        result = build({})

        self.assertEqual(result.fill, {})
        self.assertEqual(result.report, [])
        self.assertIsNone(result.bank)
        self.assertEqual(result.resume_lines, [])


class TestAddressFill(unittest.TestCase):
    def test_address_parts_are_filled_and_reported_separately(self):
        result = build({"current_address": ADDRESS})

        self.assertEqual(
            result.fill,
            {
                "private_street": "14 Nandi Durga Road, Benson Town",
                "private_city": "Bengaluru",
                "private_zip": "560046",
                "private_country_id": INDIA_ID,
                "private_state_id": KARNATAKA_ID,
            },
        )
        filled = rows(result, fill.FILLED)
        self.assertEqual(
            set(filled),
            {
                "Current Address (Street)",
                "Current Address (City)",
                "Current Address (PIN)",
                "Current Address (Country)",
                "Current Address (State)",
            },
        )
        self.assertEqual(filled["Current Address (State)"].value, "Karnataka")

    def test_an_existing_part_is_kept_and_the_rest_filled(self):
        result = build(
            {"current_address": ADDRESS},
            start={"private_city": "Mysuru", "private_country_id": (INDIA_ID, "India")},
        )

        self.assertNotIn("private_city", result.fill)
        self.assertNotIn("private_country_id", result.fill)
        self.assertEqual(result.fill["private_state_id"], KARNATAKA_ID)
        self.assertEqual(rows(result)["Current Address (City)"].outcome, fill.SKIPPED_DIFFERENT)
        self.assertNotIn("Current Address (Country)", rows(result))

    def test_country_without_a_single_match_is_invalid(self):
        for found, reason in (([], fill.NO_MATCH), ([1, 2], fill.SEVERAL_MATCHES)):
            with self.subTest(found=found):
                result = build(
                    {"current_address": ADDRESS},
                    matches={"country": {"India": found}, "state": {}},
                )
                self.assertNotIn("private_country_id", result.fill)
                self.assertEqual(rows(result)["Current Address (Country)"].reason, reason)

    def test_state_is_matched_only_within_the_country(self):
        result = build(
            {"current_address": ADDRESS},
            start={"private_country_id": (US_ID, "United States")},
        )

        self.assertNotIn("private_state_id", result.fill)
        self.assertEqual(rows(result)["Current Address (Country)"].outcome, fill.SKIPPED_DIFFERENT)
        self.assertEqual(rows(result)["Current Address (Country)"].current_value, "United States")
        self.assertEqual(rows(result)["Current Address (State)"].reason, fill.NO_MATCH)

    def test_several_states_are_invalid(self):
        matches = {
            "country": {"India": [INDIA_ID]},
            "state": {(INDIA_ID, "Karnataka"): [1, 2]},
        }
        result = build({"current_address": ADDRESS}, matches=matches)

        self.assertEqual(rows(result)["Current Address (State)"].reason, fill.SEVERAL_MATCHES)

    def test_address_names_are_offered_for_lookup(self):
        self.assertEqual(fill.address_names({"current_address": ADDRESS}), ("India", "Karnataka"))
        self.assertEqual(fill.address_names({}), (None, None))


class TestCreatedOnSave(unittest.TestCase):
    def test_bank_account_needs_a_number(self):
        result = build({"bank_name": "HDFC Bank", "ifsc_code": "HDFC0000123"})

        self.assertIsNone(result.bank)
        invalid = rows(result, fill.SKIPPED_INVALID)
        self.assertEqual(invalid["Bank Name"].reason, fill.NO_ACCOUNT_NUMBER)

    def test_bank_values_are_taken_as_read(self):
        result = build(
            {
                "bank_ac_no": "50100247731902",
                "bank_name": "Hdfc bank ltd",
                "ifsc_code": "HDFC0000123",
            }
        )

        self.assertEqual(
            result.bank,
            {
                "account_number": "50100247731902",
                "bank_name": "Hdfc bank ltd",
                "clearing_number": "HDFC0000123",
            },
        )
        self.assertEqual(result.report, [])

    def test_an_invalid_ifsc_is_omitted_and_reported(self):
        result = build({"bank_ac_no": "50100247731902", "ifsc_code": "HDFC123"})

        self.assertEqual(result.bank, {"account_number": "50100247731902"})
        row = rows(result)["IFSC Code"]
        self.assertEqual(row.outcome, fill.SKIPPED_INVALID)
        self.assertEqual(row.reason, fill.INVALID_IFSC)

    def test_resume_lines_need_their_key_values(self):
        result = build(
            {
                "education.degree": "B.Tech",
                "education.institution": "RV College",
                "education.year": "2019",
                "external_work_history.employer": "Acme Corp",
                "external_work_history.designation": "Engineer",
            }
        )

        education, experience = result.resume_lines
        self.assertEqual(education["line_type"], "education")
        self.assertEqual(education["name"], "B.Tech, RV College")
        self.assertEqual(education["date_start"], "2019-01-01")
        self.assertEqual(experience["line_type"], "experience")
        self.assertEqual(experience["name"], "Acme Corp")
        self.assertEqual(experience["details"], {"designation": "Engineer"})

    def test_incomplete_resume_lines_are_not_created(self):
        result = build(
            {
                "education.year": "2019",
                "external_work_history.designation": "Engineer",
            }
        )

        self.assertEqual(result.resume_lines, [])
        invalid = rows(result, fill.SKIPPED_INVALID)
        self.assertEqual(invalid["Education"].reason, fill.INCOMPLETE_EDUCATION)
        self.assertEqual(invalid["Previous Employment"].reason, fill.INCOMPLETE_EXPERIENCE)

    def test_institution_alone_is_enough_for_education(self):
        result = build({"education.institution": "RV College"})

        self.assertEqual(result.resume_lines[0]["name"], "RV College")
        self.assertIsNone(result.resume_lines[0]["date_start"])


class TestTargets(unittest.TestCase):
    def test_targets_cover_the_address_parts_and_skip_created_values(self):
        targets = fill.employee_targets()

        self.assertIn("private_state_id", targets)
        self.assertIn("identification_id", targets)
        self.assertNotIn("private_address", targets)
        self.assertFalse([t for t in targets if t.startswith(("bank.", "resume."))])
