import unittest

from core.masking import mask_aadhaar, mask_runs, mask_tree, national_phone


class TestMaskAadhaar(unittest.TestCase):
    def test_twelve_digits_with_spaces_masks_to_last_four(self):
        self.assertEqual(mask_aadhaar("2345 6789 0123"), "XXXX XXXX 0123")

    def test_twelve_digits_with_hyphens_masks_to_last_four(self):
        self.assertEqual(mask_aadhaar("2345-6789-0123"), "XXXX XXXX 0123")

    def test_twelve_digits_with_no_separators_masks_to_last_four(self):
        self.assertEqual(mask_aadhaar("234567890123"), "XXXX XXXX 0123")

    def test_other_groupings_mask_to_last_four(self):
        for value in ("2345 67890123", "23 45 67 89 01 23", " 2345 6789 0123 "):
            self.assertEqual(mask_aadhaar(value), "XXXX XXXX 0123", msg=value)

    def test_wrong_digit_count_is_unreadable(self):
        for value in ("2345 6789 012", "2345 6789 01234", ""):
            self.assertEqual(mask_aadhaar(value), "unreadable", msg=value)

    def test_non_digit_characters_are_unreadable(self):
        self.assertEqual(mask_aadhaar("2345-6789-012X"), "unreadable")

    def test_non_string_is_unreadable(self):
        for value in (None, 234567890123, ["2345", "6789", "0123"]):
            self.assertEqual(mask_aadhaar(value), "unreadable", msg=repr(value))


if __name__ == "__main__":
    unittest.main()


class TestMaskRuns(unittest.TestCase):
    def test_every_separator_spelling_is_masked(self):
        for text in (
            "2345 6789 0123",
            "2345  6789 0123",
            "2345.6789.0123",
            "2345/6789/0123",
            "2345 - 6789 - 0123",
            "234567890123",
        ):
            with self.subTest(text=text):
                self.assertEqual(mask_runs(f"Aadhaar {text}."), "Aadhaar XXXX XXXX 0123.")

    def test_shorter_and_longer_numbers_are_left_alone(self):
        for text in ("98450 12345", "50100247731902", "1997-11-09", "560046"):
            with self.subTest(text=text):
                self.assertEqual(mask_runs(text), text)


class TestMaskTree(unittest.TestCase):
    def test_every_string_key_and_number_is_masked(self):
        tree = {
            "result": {"remark": "Aadhaar 2345.6789.0123", "234567890123": True},
            "extractions": [{"aadhaar": 234567890123}, "2345  6789 0123"],
            "confidence": 0.93,
            "ok": True,
            "none": None,
        }

        masked = mask_tree(tree)

        self.assertEqual(
            masked,
            {
                "result": {"remark": "Aadhaar XXXX XXXX 0123", "XXXX XXXX 0123": True},
                "extractions": [{"aadhaar": "XXXX XXXX 0123"}, "XXXX XXXX 0123"],
                "confidence": 0.93,
                "ok": True,
                "none": None,
            },
        )


class TestNationalPhone(unittest.TestCase):
    def test_the_country_code_is_dropped_from_a_twelve_digit_mobile(self):
        for text, expected in (
            ("+91 98765 43210", "98765 43210"),
            ("+91-9876543210", "9876543210"),
            ("91 98765 43210", "98765 43210"),
            ("+91 (98765) 43210", "+91 (98765) 43210"),
        ):
            with self.subTest(text=text):
                self.assertEqual(national_phone(text), expected)

    def test_other_numbers_are_unchanged(self):
        for text in (
            "98765 43210",
            "+1 415 555 0100",
            "+44 20 7946 0958",
            "2345 6789 0123",
            "9187 6543 2101",
            "919876543210",
        ):
            with self.subTest(text=text):
                self.assertEqual(national_phone(text), text)
