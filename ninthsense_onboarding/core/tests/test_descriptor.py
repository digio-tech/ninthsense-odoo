import datetime
import unittest
from pathlib import Path

from core import descriptor, portal_contract

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"
ACCEPT = (".pdf", ".jpg", ".jpeg", ".png")


def _request_view(**overrides):
    defaults = dict(
        ref="ONB-2026-0042",
        expires_at=datetime.datetime(2026, 9, 18, 10, 0, 0, tzinfo=datetime.UTC),
        instance_url="https://hr.example.com",
        display_name="Priya",
    )
    defaults.update(overrides)
    return descriptor.RequestView(**defaults)


def _lines():
    return [
        descriptor.LineView(
            code="aadhaar_front",
            label="Aadhaar Card (Front)",
            order=1,
            mandatory=True,
            accept=ACCEPT,
            max_mb=3,
            verification_document_id=None,
        ),
        descriptor.LineView(
            code="pan_card",
            label="PAN Card",
            order=2,
            mandatory=False,
            accept=ACCEPT,
            max_mb=5,
            verification_document_id="doc-123",
        ),
    ]


def _branding():
    return descriptor.Branding(
        org_name="Example Co", logo_url="https://hr.example.com/logo.png?company=1"
    )


class TestBuild(unittest.TestCase):
    def setUp(self):
        self.validators = portal_contract.load_validators(SCHEMA_DIR)

    def _build(self, state="open", lines=None, **view):
        lines = _lines() if lines is None else lines
        return descriptor.build(_request_view(**view), lines, state, _branding())

    def test_open_descriptor_passes_the_request_schema(self):
        portal_contract.validate_descriptor(self.validators, self._build())

    def test_goal_and_stage_are_fixed(self):
        result = self._build()
        self.assertEqual(result["goal_key"], "onboarding")
        self.assertEqual(result["stage"], "Onboarding")

    def test_state_follows_the_portal_state(self):
        for state in ("open", "submitted", "expired"):
            with self.subTest(state=state):
                self.assertEqual(self._build(state)["state"], state)

    def test_hrms_names_odoo_and_the_instance(self):
        self.assertEqual(
            self._build()["hrms"], {"system": "odoo", "instance": "https://hr.example.com"}
        )

    def test_max_bytes_is_max_mb_times_1048576(self):
        documents = self._build()["steps"][0]["documents"]
        self.assertEqual([d["max_bytes"] for d in documents], [3 * 1048576, 5 * 1048576])

    def test_lines_appear_in_the_order_given_with_their_flags(self):
        documents = self._build()["steps"][0]["documents"]
        self.assertEqual([d["document_code"] for d in documents], ["aadhaar_front", "pan_card"])
        self.assertEqual([d["order"] for d in documents], [1, 2])
        self.assertEqual([d["mandatory"] for d in documents], [True, False])

    def test_verification_document_id_only_on_filled_lines(self):
        documents = self._build()["steps"][0]["documents"]
        self.assertNotIn("verification_document_id", documents[0])
        self.assertEqual(documents[1]["verification_document_id"], "doc-123")

    def test_submitted_and_expired_carry_no_documents_and_pass(self):
        for state in ("submitted", "expired"):
            with self.subTest(state=state):
                result = self._build(state)
                self.assertEqual(result["steps"][0]["documents"], [])
                portal_contract.validate_descriptor(self.validators, result)

    def test_expires_at_ends_with_z_and_is_omitted_when_unknown(self):
        self.assertEqual(self._build()["expires_at"], "2026-09-18T10:00:00Z")
        self.assertNotIn("expires_at", self._build(expires_at=None))

    def test_subject_is_omitted_without_a_name(self):
        self.assertEqual(self._build()["subject"], {"display_name": "Priya"})
        self.assertNotIn("subject", self._build(display_name=None))

    def test_callback_path_is_fixed(self):
        self.assertEqual(
            self._build()["completion"]["callback_path"],
            "/api/method/ninthsense.document_collection.portal_api.store_verification",
        )

    def test_branding_comes_from_the_given_company_values(self):
        self.assertEqual(
            self._build()["branding"],
            {"org_name": "Example Co", "logo_url": "https://hr.example.com/logo.png?company=1"},
        )
        result = descriptor.build(
            _request_view(), _lines(), "open", descriptor.Branding(org_name="Example Co")
        )
        self.assertEqual(result["branding"], {"org_name": "Example Co"})


class TestAcceptExtensions(unittest.TestCase):
    def test_normalises_case_dots_and_repeats(self):
        self.assertEqual(
            descriptor.accept_extensions(" PDF, .jpg,.JPG,, png "), (".pdf", ".jpg", ".png")
        )

    def test_empty_is_no_extensions(self):
        self.assertEqual(descriptor.accept_extensions(None), ())


if __name__ == "__main__":
    unittest.main()
