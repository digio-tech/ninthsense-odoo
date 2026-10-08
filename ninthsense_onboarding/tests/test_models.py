import datetime

from odoo.addons.base.tests.common import BaseCommon
from odoo.exceptions import ValidationError

from .test_send import default_template, hired_applicant


class TestOnboardingModels(BaseCommon):
    _test_user_groups = ("base.group_user", "hr_recruitment.group_hr_recruitment_manager")

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(user=cls._test_user)
        cls.Request = cls.env["ninthsense.onboarding.request"]
        cls.applicant = hired_applicant(
            cls.env, {"partner_name": "Asha Rao", "email_from": "asha@example.com"}
        )

    def _request(self, **vals):
        vals.setdefault("company_id", self.env.company.id)
        vals.setdefault("applicant_id", self.applicant.id)
        # Only the app creates requests, as superuser.
        return self.Request.sudo().create(vals)

    def test_sequence_assigns_ref(self):
        year = str(datetime.date.today().year)
        first = self._request(applicant_id=False)
        second = self._request(applicant_id=False)
        self.assertTrue(first.ref.startswith(f"ONB-{year}-"))
        self.assertNotEqual(first.ref, second.ref)

    def test_one_open_request_per_applicant(self):
        first = self._request()
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._request()
        first._ninthsense_cancel("refused")
        self.assertEqual(first.state, "cancelled")
        self.assertEqual(first.cancel_reason, "refused")
        self.assertFalse(first.sudo().link_hash)
        self.assertEqual(self._request().state, "link_sent")

    def test_portal_state(self):
        now = datetime.datetime(2026, 1, 10)
        request = self._request(link_expires_at=now + datetime.timedelta(days=1))
        self.assertEqual(request._ninthsense_portal_state(now), "open")
        self.assertEqual(
            request._ninthsense_portal_state(now + datetime.timedelta(days=2)), "expired"
        )
        request.state = "data_received"
        self.assertEqual(
            request._ninthsense_portal_state(now + datetime.timedelta(days=2)), "submitted"
        )
        request.state = "completed"
        self.assertEqual(request._ninthsense_portal_state(now), "revoked")
        request.state = "cancelled"
        self.assertEqual(request._ninthsense_portal_state(now), "revoked")

    def test_link_expired_flag(self):
        past = datetime.datetime(2000, 1, 1)
        request = self._request(link_expires_at=past)
        self.assertTrue(request.link_expired)
        request.state = "data_received"
        self.assertFalse(request.link_expired)

    def test_installed_template_lines(self):
        template = self.env.ref("ninthsense_onboarding.template_onboarding")
        expected = [
            ("aadhaar_front", True, ".pdf,.jpg,.jpeg,.png"),
            ("aadhaar_back", False, ".pdf,.jpg,.jpeg,.png"),
            ("pan_card", True, ".pdf,.jpg,.jpeg,.png"),
            ("resume", True, ".pdf"),
            ("graduation_certificate", True, ".pdf,.jpg,.jpeg,.png"),
            ("latest_pay_slip", False, ".pdf"),
            ("cancelled_cheque", True, ".pdf,.jpg,.jpeg,.png"),
            ("bank_statement", False, ".pdf"),
            ("passport", False, ".pdf"),
        ]
        actual = [
            (line.document_type_id.code, line.mandatory, line.accept) for line in template.line_ids
        ]
        self.assertEqual(actual, expected)
        self.assertEqual({line.max_mb for line in template.line_ids}, {3})
        self.assertEqual(self.env["ninthsense.onboarding.document.type"].search_count([]), 14)

    def test_snapshot_lines(self):
        template = default_template(self.env)
        request = self._request()
        request._ninthsense_snapshot_lines(template)
        self.assertEqual(request.template_id, template)
        self.assertEqual(
            request.line_ids.mapped("code"), template.line_ids.document_type_id.mapped("code")
        )
        with self.assertRaises(ValidationError), self.cr.savepoint():
            request.line_ids[0].max_mb = 21

    def test_form_renders_empty_states(self):
        view = self.env.ref("ninthsense_onboarding.onboarding_request_view_form")
        arch = self.Request.get_view(view.id, "form")["arch"]
        for text in ("No documents yet", "No data received yet", "No fill report yet"):
            self.assertIn(text, arch)
        self.assertIn('name="source_name"', arch)
        self.assertIn('name="template_id"', arch)
        labels = dict(self.env["ninthsense.onboarding.fill.line"]._fields["outcome"].selection)
        self.assertEqual(
            list(labels.values()),
            [
                "Filled",
                "Skipped — already filled",
                "Skipped — invalid",
                "Created on save",
                "Attachments that failed",
            ],
        )

    def test_a_parsed_value_names_its_document(self):
        request = self._request()
        value = (
            self.env["ninthsense.onboarding.value"]
            .sudo()
            .create(
                {
                    "request_id": request.id,
                    "field_key": "date_of_birth",
                    "value": "1997-11-09",
                    "source_code": "passport",
                }
            )
        )
        self.assertEqual(value.source_name, "Passport")
