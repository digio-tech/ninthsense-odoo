from odoo.addons.base.tests.common import BaseCommon
from odoo.fields import Command
from odoo.tests import HttpCase, tagged

from .portal_helpers import (
    PREFIX,
    completion_payload,
    envelope,
    send_link,
    signed_headers,
)
from .test_send import HIRED_STAGE_XMLID, configure_portal, hired_applicant


class TestCancelOnApplicantChange(BaseCommon):
    _test_user_groups = ("base.group_user", "hr_recruitment.group_hr_recruitment_user")

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        configure_portal(cls.env)
        cls.env = cls.env(user=cls._test_user)

    def _applicant_with_link(self, name="Asha Rao"):
        applicant = hired_applicant(
            self.env,
            {"partner_name": name, "email_from": f"{name.split()[0].lower()}@example.test"},
        )
        applicant.action_send_onboarding_link()
        request = applicant.onboarding_request_id
        self.assertEqual(request.state, "link_sent")
        self.assertTrue(request.sudo().link_hash)
        return applicant, request

    def _assert_cancelled(self, request, reason):
        request.invalidate_recordset()
        self.assertEqual(request.state, "cancelled")
        self.assertEqual(request.cancel_reason, reason)
        self.assertFalse(request.sudo().link_hash)

    def _refuse(self, applicant):
        reason = self.env["hr.applicant.refuse.reason"].search([], limit=1)
        wizard = self.env["applicant.refuse.single"].create(
            {
                "applicant_ids": [Command.set(applicant.ids)],
                "refuse_reason_id": reason.id,
                "send_mail": False,
            }
        )
        wizard.action_refuse_reason_apply()

    def test_archive_cancels_the_open_request(self):
        applicant, request = self._applicant_with_link()
        applicant.action_archive()
        self._assert_cancelled(request, "archived")

    def test_refuse_through_the_wizard_cancels_as_refused(self):
        applicant, request = self._applicant_with_link()
        self._refuse(applicant)
        self.assertFalse(applicant.active)
        self._assert_cancelled(request, "refused")

    def test_delete_cancels_and_keeps_the_applicant_details(self):
        applicant, request = self._applicant_with_link()
        applicant_id = applicant.id
        applicant.unlink()
        self._assert_cancelled(request, "deleted")
        self.assertFalse(request.applicant_id)
        self.assertEqual(request.applicant_ref, applicant_id)
        self.assertEqual(request.applicant_name, "Asha Rao")

    def test_data_received_request_is_cancelled_too(self):
        applicant, request = self._applicant_with_link()
        request.sudo().state = "data_received"
        applicant.action_archive()
        self._assert_cancelled(request, "archived")

    def test_restore_keeps_the_request_cancelled_and_send_starts_a_new_one(self):
        applicant, request = self._applicant_with_link()
        applicant.action_archive()
        applicant.action_unarchive()
        self.assertEqual(request.state, "cancelled")
        # Restoring puts the applicant back in the first stage, so HR hires again.
        applicant.stage_id = self.env.ref(HIRED_STAGE_XMLID)

        applicant.action_send_onboarding_link()

        fresh = applicant.onboarding_request_id
        self.assertNotEqual(fresh, request)
        self.assertEqual(fresh.state, "link_sent")
        self.assertEqual(request.state, "cancelled")

    def test_completed_requests_are_untouched_by_archive(self):
        applicant, request = self._applicant_with_link()
        request.sudo().state = "completed"
        applicant.action_archive()
        self.assertEqual(request.state, "completed")
        self.assertIsNone(request.cancel_reason or None)

    def test_archive_leaves_other_applicants_alone(self):
        applicant, request = self._applicant_with_link()
        other, other_request = self._applicant_with_link("Ben Kumar")
        applicant.action_archive()
        self.assertEqual(other_request.state, "link_sent")
        self.assertTrue(other_request.sudo().link_hash)


@tagged("post_install", "-at_install")
class TestCancelledLinkIsDead(HttpCase):
    def test_portal_routes_answer_not_found_after_archive(self):
        applicant = hired_applicant(
            self.env, {"partner_name": "Priya Raghavan", "email_from": "priya.cancel@example.test"}
        )
        request, token = send_link(self.env, applicant)
        applicant.action_archive()
        self.assertEqual(request.state, "cancelled")

        response = self.url_open(PREFIX + "get_request", params={"token": token})
        self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(response.json(), {"error": {"code": "invalid_token"}})

        raw = envelope(token, completion_payload(request, []))
        response = self.url_open(
            PREFIX + "store_verification", data=raw, headers=signed_headers(raw)
        )
        self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(response.json(), {"error": {"code": "invalid_token"}})
