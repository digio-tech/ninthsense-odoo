import re

from odoo.tests import HttpCase, new_test_user, tagged

from .portal_helpers import post_documents, post_verification, send_link
from .test_create_employee import OFFICER_GROUPS
from .test_send import hired_applicant

#: Twelve digits, separated by any run of spaces, dots, hyphens or slashes.
TWELVE_DIGITS = re.compile(r"\d(?:[\s./-]*\d){11}")
CORRELATION_ID = re.compile(r'"correlation_id": "[^"]*"')
AADHAAR_NUMBER = "2345 6789 0123"
MOBILE = "+91 98765 43210"
# A SHA-256 hex digest is opaque by construction, so a coincidental run of
# twelve digits in it is not a readable value of anything.
EXEMPT_FIELDS = {("ninthsense.onboarding.request", "link_hash")}
SCANNED_TYPES = ("char", "text", "html", "json")


@tagged("post_install", "-at_install")
class TestNoFullAadhaar(HttpCase):
    def _last_mail_id(self):
        mails = self.env(su=True)["mail.mail"].with_context(active_test=False)
        return mails.search([], order="id desc", limit=1).id or 0

    def _offenders(self, after_mail_id):
        """Stored values holding twelve digits; of the mails, only those after `after_mail_id`."""
        env = self.env(su=True)
        found = []
        models = [
            env[name]
            for name in env.registry
            if name.startswith("ninthsense.onboarding.") and env[name]._auto
        ]
        scanned = [(model, ("identification_id",)) for model in (env["hr.employee"],)]
        for model in models:
            names = [
                name
                for name, field in model._fields.items()
                if field.type in SCANNED_TYPES
                and field.store
                and (model._name, name) not in EXEMPT_FIELDS
            ]
            scanned.append((model, names))
        for model, names in scanned:
            for record in model.with_context(active_test=False).search([]):
                for name in names:
                    value = record[name]
                    if value and TWELVE_DIGITS.search(str(value)):
                        found.append(f"{model._name}#{record.id}.{name}")
        attachments = env["ir.attachment"].search(
            [("res_model", "in", ("ninthsense.onboarding.request", "hr.employee"))]
        )
        for attachment in attachments:
            if TWELVE_DIGITS.search(attachment.name or ""):
                found.append(f"ir.attachment#{attachment.id}.name")
        mails = (
            env["mail.mail"].with_context(active_test=False).search([("id", ">", after_mail_id)])
        )
        for mail in mails:
            for name in ("body_html", "body", "subject"):
                if mail[name] and TWELVE_DIGITS.search(mail[name]):
                    found.append(f"mail.mail#{mail.id}.{name}")
        return found

    def test_no_full_aadhaar_number_is_stored_or_logged_after_the_full_flow(self):
        applicant = hired_applicant(
            self.env, {"partner_name": "Priya Raghavan", "email_from": "priya.aadhaar@example.test"}
        )
        last_mail_id = self._last_mail_id()
        with self.assertLogs("odoo.addons.ninthsense_onboarding", level="DEBUG") as captured:
            request, token = send_link(self.env, applicant)
            post_documents(self, request, token)
            post_verification(
                self,
                request,
                token,
                {
                    "aadhaar_front": {"aadhaar_number": AADHAAR_NUMBER, "name": "Priya Raghavan"},
                    "pan_card": {"name": "Priya Raghavan 2345  6789 0123"},
                    "resume": {"phone": MOBILE},
                },
                result={
                    "remark": f"Aadhaar {AADHAAR_NUMBER.replace(' ', '')}",
                    "ocr": ["2345  6789 0123", "2345.6789.0123", "2345/6789/0123"],
                },
            )
            self.env.invalidate_all()

            officer = new_test_user(self.env, login="onb_aadhaar_officer", groups=OFFICER_GROUPS)
            applicant = applicant.with_user(officer)
            applicant.create_employee_from_applicant()
            employee = applicant.employee_id

        self.assertEqual(employee.identification_id, "XXXX XXXX 0123")
        self.assertEqual(employee.private_phone, "98765 43210")
        self.assertEqual(request.state, "completed")
        self.assertFalse(self._offenders(last_mail_id))
        # A correlation id is a random UUID, whose digit runs can look like a number by chance.
        output = CORRELATION_ID.sub("", "\n".join(captured.output))
        self.assertIsNone(TWELVE_DIGITS.search(output))

    def test_the_scan_pattern_finds_every_spelling(self):
        for text in ("2345 6789 0123", "2345  6789 0123", "2345.6789.0123", "234567890123"):
            with self.subTest(text=text):
                self.assertTrue(TWELVE_DIGITS.search(f"x {text} y"))
        self.assertFalse(TWELVE_DIGITS.search("98765 43210"))
