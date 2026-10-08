from odoo.addons.base.tests.common import BaseCommon
from odoo.exceptions import AccessError
from odoo.tests import new_test_user

from .test_create_employee import receive_data
from .test_send import configure_portal, hired_applicant

MENUS = ("menu_onboarding_requests", "menu_onboarding_template")


class TestAccess(BaseCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        configure_portal(cls.env)
        cls.interviewer = new_test_user(
            cls.env,
            login="onb_interviewer",
            groups="base.group_user,hr_recruitment.group_hr_recruitment_interviewer",
        )
        cls.recruiter = new_test_user(
            cls.env,
            login="onb_recruiter_only",
            groups="base.group_user,hr_recruitment.group_hr_recruitment_user",
        )
        cls.applicant = hired_applicant(
            cls.env, {"partner_name": "Asha Rao", "email_from": "asha.access@example.test"}
        )

    def _onboarding_models(self):
        names = [name for name in self.env.registry if name.startswith("ninthsense.onboarding.")]
        self.assertTrue(names)
        return names

    def test_interviewer_cannot_read_any_onboarding_model(self):
        for name in self._onboarding_models():
            with self.subTest(model=name):
                self.assertFalse(self.env[name].with_user(self.interviewer).has_access("read"))
                with self.assertRaises(AccessError):
                    self.env[name].with_user(self.interviewer).search([])

    def test_interviewer_sees_no_send_button_page_or_menu(self):
        views = self.env["hr.applicant"].with_user(self.interviewer).get_views([(False, "form")])
        arch = views["views"]["form"]["arch"]
        self.assertNotIn("action_send_onboarding_link", arch)
        self.assertNotIn("onboarding_request", arch)
        self.assertNotIn('name="onboarding"', arch)

        visible = self.env["ir.ui.menu"].with_user(self.interviewer)._visible_menu_ids()
        for menu in MENUS:
            with self.subTest(menu=menu):
                self.assertNotIn(self.env.ref(f"ninthsense_onboarding.{menu}").id, visible)

    def test_recruiter_sees_the_send_button_page_and_menus(self):
        views = self.env["hr.applicant"].with_user(self.recruiter).get_views([(False, "form")])
        arch = views["views"]["form"]["arch"]
        self.assertIn("action_send_onboarding_link", arch)
        self.assertIn('name="onboarding"', arch)

        visible = self.env["ir.ui.menu"].with_user(self.recruiter)._visible_menu_ids()
        for menu in MENUS:
            with self.subTest(menu=menu):
                self.assertIn(self.env.ref(f"ninthsense_onboarding.{menu}").id, visible)

    def test_recruiter_without_employee_access_cannot_create_an_employee(self):
        self.assertFalse(self.recruiter.has_group("hr.group_hr_user"))
        applicant = self.applicant.with_user(self.recruiter)
        applicant.action_send_onboarding_link()
        request = receive_data(applicant.sudo().onboarding_request_id)

        with self.assertRaises(AccessError):
            applicant.create_employee_from_applicant()

        self.assertFalse(applicant.sudo().employee_id)
        self.assertEqual(request.state, "data_received")
        self.assertFalse(request.fill_line_ids)

    def test_officer_reads_but_cannot_change_what_the_app_stores(self):
        applicant = self.applicant.with_user(self.recruiter)
        applicant.action_send_onboarding_link()
        request = receive_data(applicant.sudo().onboarding_request_id).with_user(self.recruiter)
        value = request.value_ids.filtered(lambda value: value.field_key == "bank_ac_no")
        self.assertEqual(value.value, "50100247731902")

        for label, write in (
            ("link expiry", lambda: request.write({"link_expires_at": "2099-01-01 00:00:00"})),
            ("company", lambda: request.write({"company_id": self.env.company.id})),
            ("state", lambda: request.write({"state": "completed"})),
            ("value", lambda: value.write({"value": "99999999999999"})),
            ("value create", lambda: value.create({"request_id": request.id, "field_key": "x"})),
            ("document", lambda: request.document_ids[:1].write({"code": "pan_card"})),
            ("line", lambda: request.line_ids[:1].write({"max_mb": 20})),
            (
                "fill line",
                lambda: value.env["ninthsense.onboarding.fill.line"].create(
                    {"request_id": request.id}
                ),
            ),
        ):
            with self.subTest(label), self.assertRaises(AccessError):
                write()
        self.assertEqual(value.sudo().value, "50100247731902")

        request.message_post(body="A note from the officer")
        self.assertIn("A note from the officer", request.message_ids[:1].body)
