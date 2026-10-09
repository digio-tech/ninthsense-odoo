import unittest

from core import mapping_rules
from core.catalogue import ENTRIES
from core.mapping_rules import (
    FALLBACK_IS_SOURCE,
    FALLBACK_NOT_ALLOWED,
    MAPPED_TWICE,
    SOURCE_NOT_ALLOWED,
    UNKNOWN_FIELD,
    Problem,
    allowed_sources,
    choose,
    mapping_problems,
)

CODES = ("aadhaar_front", "pan_card", "passport", "resume")


class TestAllowedSources(unittest.TestCase):
    def test_the_template_documents_that_can_supply_the_key_in_catalogue_order(self):
        self.assertEqual(
            allowed_sources("date_of_birth", ("resume", "passport", "pan_card")),
            ("pan_card", "passport", "resume"),
        )

    def test_a_key_none_of_the_documents_supply_has_no_source(self):
        self.assertEqual(allowed_sources("bank_ac_no", CODES), ())

    def test_an_unknown_key_has_no_source(self):
        self.assertEqual(allowed_sources("salary", CODES), ())


class TestMappingProblems(unittest.TestCase):
    def test_a_valid_mapping_has_no_problems(self):
        rows = [
            ("date_of_birth", "passport", "aadhaar_front"),
            ("legal_name", "aadhaar_front", None),
        ]
        self.assertEqual(mapping_problems(rows, CODES), [])

    def test_an_empty_mapping_has_no_problems(self):
        self.assertEqual(mapping_problems([], CODES), [])

    def test_an_unknown_field(self):
        self.assertEqual(
            mapping_problems([("salary", "resume", None)], CODES),
            [Problem(UNKNOWN_FIELD, "salary")],
        )

    def test_a_field_mapped_twice_is_reported_once(self):
        rows = [
            ("date_of_birth", "passport", None),
            ("date_of_birth", "aadhaar_front", None),
        ]
        self.assertEqual(mapping_problems(rows, CODES), [Problem(MAPPED_TWICE, "date_of_birth")])

    def test_a_source_that_cannot_supply_the_field(self):
        self.assertEqual(
            mapping_problems([("passport_number", "pan_card", None)], CODES),
            [Problem(SOURCE_NOT_ALLOWED, "passport_number")],
        )

    def test_a_source_not_in_the_template(self):
        self.assertEqual(
            mapping_problems([("bank_ac_no", "cancelled_cheque", None)], CODES),
            [Problem(SOURCE_NOT_ALLOWED, "bank_ac_no")],
        )

    def test_a_missing_source(self):
        self.assertEqual(
            mapping_problems([("legal_name", None, None)], CODES),
            [Problem(SOURCE_NOT_ALLOWED, "legal_name")],
        )

    def test_a_fallback_not_allowed(self):
        rows = [("sex", "aadhaar_front", "pan_card"), ("legal_name", "pan_card", "aadhaar_back")]
        self.assertEqual(
            mapping_problems(rows, CODES),
            [Problem(FALLBACK_NOT_ALLOWED, "sex"), Problem(FALLBACK_NOT_ALLOWED, "legal_name")],
        )

    def test_a_fallback_equal_to_the_source(self):
        self.assertEqual(
            mapping_problems([("legal_name", "pan_card", "pan_card")], CODES),
            [Problem(FALLBACK_IS_SOURCE, "legal_name")],
        )


class TestChoose(unittest.TestCase):
    VALUES = {
        ("date_of_birth", "aadhaar_front"): "1997-11-09",
        ("date_of_birth", "passport"): "1997-11-10",
        ("legal_name", "pan_card"): "Priya Raghavan",
    }

    def test_the_source_wins(self):
        rows = [("date_of_birth", "passport", "aadhaar_front")]
        self.assertEqual(choose(self.VALUES, rows), {"date_of_birth": "1997-11-10"})

    def test_the_fallback_is_used_when_the_source_has_no_value(self):
        rows = [("legal_name", "aadhaar_front", "pan_card")]
        self.assertEqual(choose(self.VALUES, rows), {"legal_name": "Priya Raghavan"})

    def test_an_empty_source_value_falls_back(self):
        values = {**self.VALUES, ("legal_name", "aadhaar_front"): ""}
        rows = [("legal_name", "aadhaar_front", "pan_card")]
        self.assertEqual(choose(values, rows), {"legal_name": "Priya Raghavan"})

    def test_nothing_when_neither_document_has_a_value(self):
        self.assertEqual(choose(self.VALUES, [("sex", "aadhaar_front", None)]), {})

    def test_an_unmapped_key_gives_nothing(self):
        rows = [("legal_name", "pan_card", None)]
        self.assertEqual(choose(self.VALUES, rows), {"legal_name": "Priya Raghavan"})

    def test_no_rows_give_nothing(self):
        self.assertEqual(choose(self.VALUES, []), {})


class TestDefaultRows(unittest.TestCase):
    def test_every_key_the_documents_supply_gets_its_first_two_sources(self):
        rows = mapping_rules.default_rows(CODES)
        self.assertEqual(mapping_problems(rows, CODES), [])
        by_key = {key: (source, fallback) for key, source, fallback in rows}
        self.assertEqual(by_key["date_of_birth"], ("aadhaar_front", "pan_card"))
        self.assertEqual(by_key["sex"], ("aadhaar_front", None))
        supplied = {entry.key for entry in ENTRIES if allowed_sources(entry.key, CODES)}
        self.assertEqual(set(by_key), supplied)


if __name__ == "__main__":
    unittest.main()
