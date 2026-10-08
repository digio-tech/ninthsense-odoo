from odoo.addons.base.tests.common import BaseCommon
from odoo.tests import new_test_user

from .test_send import configure_portal, hired_applicant


class TestInviteState(BaseCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        configure_portal(cls.env)
        applicant = hired_applicant(
            cls.env, {"partner_name": "Asha Rao", "email_from": "asha@example.com"}
        )
        applicant.action_send_onboarding_link()
        cls.request = applicant.onboarding_request_id
        cls.mail_id = cls.request.invite_mail_id.id

    def test_invite_state_follows_the_mail(self):
        expected = {
            "outgoing": "queued",
            "sent": "sent",
            "received": "sent",
            "exception": "failed",
            "cancel": "failed",
        }
        for mail_state, invite_state in expected.items():
            with self.subTest(mail_state=mail_state):
                self.env["mail.mail"].sudo().browse(self.mail_id).write({"state": mail_state})
                self.assertEqual(self.request.invite_state, invite_state)

    def test_a_failed_email_shows_its_reason(self):
        mail = self.env["mail.mail"].sudo().browse(self.mail_id)
        mail.write({"state": "exception", "failure_reason": "[Errno 61] Connection refused"})

        self.assertEqual(self.request.invite_state, "failed")
        self.assertEqual(self.request.invite_failure, "[Errno 61] Connection refused")

    def test_no_failure_is_shown_unless_the_email_failed(self):
        mail = self.env["mail.mail"].sudo().browse(self.mail_id)
        for mail_state in ("outgoing", "sent"):
            with self.subTest(mail_state=mail_state):
                mail.write({"state": mail_state, "failure_reason": "stale reason"})
                self.request.invalidate_recordset(["invite_failure"])
                self.assertFalse(self.request.invite_failure)

    def test_an_officer_sees_the_failure_and_the_tab_marks_it(self):
        officer = new_test_user(
            self.env,
            login="invite_state_officer",
            groups="base.group_user,hr_recruitment.group_hr_recruitment_user",
        )
        mail = self.env["mail.mail"].sudo().browse(self.mail_id)
        mail.write({"state": "exception", "failure_reason": "[Errno 61] Connection refused"})

        request = self.request.with_user(officer)
        self.assertEqual(request.invite_failure, "[Errno 61] Connection refused")

        form = request.get_views([(False, "form")])["views"]["form"]["arch"]
        self.assertIn("The onboarding email could not be delivered:", form)
        self.assertIn("invisible=\"invite_state != 'failed'\"", form)
        applicant_form = (
            self.env["hr.applicant"]
            .with_user(officer)
            .get_views([(False, "form")])["views"]["form"]["arch"]
        )
        self.assertIn("decoration-danger=\"invite_state == 'failed'\"", applicant_form)
