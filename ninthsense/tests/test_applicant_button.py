from odoo.addons.base.tests.common import BaseCommon
from odoo.tests import new_test_user

from .test_send import configure_portal, hired_applicant

BUTTON = "action_open_onboarding_requests"


class TestApplicantButton(BaseCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        configure_portal(cls.env)
        cls.officer = new_test_user(
            cls.env,
            login="onb_btn_officer",
            groups="base.group_user,hr_recruitment.group_hr_recruitment_user",
        )
        cls.interviewer = new_test_user(
            cls.env,
            login="onb_btn_interviewer",
            groups="base.group_user,hr_recruitment.group_hr_recruitment_interviewer",
        )
        cls.applicant = hired_applicant(
            cls.env, {"partner_name": "Asha Rao", "email_from": "asha.button@example.test"}
        )

    def _request(self, state):
        return (
            self.env["ninthsense.onboarding.request"]
            .sudo()
            .create(
                {
                    "applicant_id": self.applicant.id,
                    "company_id": self.env.company.id,
                    "candidate_email": "asha.button@example.test",
                    "state": state,
                }
            )
        )

    def _applicant(self):
        return self.applicant.with_user(self.officer)

    def test_no_request_counts_zero_and_has_no_status(self):
        applicant = self._applicant()
        self.assertEqual(applicant.onboarding_request_count, 0)
        self.assertFalse(applicant.onboarding_latest_state)

    def test_status_is_the_open_request_over_an_older_cancelled_one(self):
        cancelled = self._request("link_sent")
        cancelled.sudo()._ninthsense_cancel("refused")
        self._request("data_received")
        self.assertEqual(self._applicant().onboarding_latest_state, "data_received")
        self.assertEqual(self._applicant().onboarding_request_count, 2)
        self.assertEqual(cancelled.state, "cancelled")

    def test_status_falls_back_to_the_most_recent_when_none_is_open(self):
        first = self._request("completed")
        second = self._request("cancelled")
        self.assertGreater(second.id, first.id)
        self.assertEqual(self._applicant().onboarding_latest_state, "cancelled")

    def test_open_request_wins_over_a_more_recent_cancelled_one(self):
        self._request("link_sent")
        self._request("cancelled")
        self.assertEqual(self._applicant().onboarding_latest_state, "link_sent")

    def test_one_request_opens_its_form(self):
        request = self._request("link_sent")
        action = self._applicant().action_open_onboarding_requests()
        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertEqual(action["res_model"], "ninthsense.onboarding.request")
        self.assertEqual(action["res_id"], request.id)
        self.assertEqual(action["view_mode"], "form")
        self.assertEqual(action["target"], "current")

    def test_several_requests_open_the_list_for_this_applicant(self):
        self._request("cancelled")
        self._request("link_sent")
        action = self._applicant().action_open_onboarding_requests()
        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertEqual(action["res_model"], "ninthsense.onboarding.request")
        self.assertEqual(action["domain"], [("applicant_id", "=", self.applicant.id)])
        self.assertNotIn("res_id", action)
        self.assertEqual([mode for _view, mode in action["views"]], ["list", "form"])

    def test_officer_form_has_the_button_and_interviewer_form_does_not(self):
        for user, expected in ((self.officer, True), (self.interviewer, False)):
            with self.subTest(user=user.login):
                views = self.env["hr.applicant"].with_user(user).get_views([(False, "form")])
                self.assertEqual(BUTTON in views["views"]["form"]["arch"], expected)

    def test_menu_sits_under_the_recruitment_root(self):
        menu = self.env.ref("ninthsense.menu_onboarding_requests")
        self.assertEqual(menu.parent_id, self.env.ref("hr_recruitment.menu_hr_recruitment_root"))
        self.assertEqual(menu.name, "Onboarding")
        self.assertEqual(menu.sequence, 3)
