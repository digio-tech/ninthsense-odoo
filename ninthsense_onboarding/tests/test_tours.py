from unittest.mock import patch

from odoo.tests import HttpCase, new_test_user, tagged
from odoo.tools import config as odoo_config

from .portal_helpers import send_link
from .test_create_employee import india_company, officer, open_request, receive_data
from .test_send import configure_portal, hired_applicant, make_template


@tagged("post_install", "-at_install")
class TestTours(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        configure_portal(cls.env)
        cls.officer = new_test_user(
            cls.env,
            login="onboarding_officer",
            groups="base.group_user,hr_recruitment.group_hr_recruitment_user",
        )

    def test_send_link_tour(self):
        foreign = make_template(
            self.env,
            "Foreign National",
            ("passport", "pan_card"),
            [("date_of_birth", "passport", "pan_card")],
        )
        # Send shows only once the applicant is hired.
        applicant = hired_applicant(
            self.env,
            {"partner_name": "Tour Candidate", "email_from": "tour.candidate@example.test"},
        )

        # No outgoing mail server, so the link dialog warns.
        self.env["ir.mail_server"].sudo().search([]).unlink()
        with patch.dict(odoo_config.options, {"smtp_server": "localhost"}):
            self.start_tour(
                f"/odoo/recruitment-applications/{applicant.id}",
                "ninthsense_onboarding_send_link_tour",
                login=self.officer.login,
            )

        self.assertEqual(len(applicant.onboarding_request_ids), 1)
        request = applicant.onboarding_request_ids
        self.assertEqual(request.template_id, foreign)
        self.assertEqual(request.line_ids.mapped("code"), ["passport", "pan_card"])
        # Closing the link dialog discards it, so the plain link is never saved.
        self.assertFalse(self.env["ninthsense.onboarding.link.dialog"].sudo().search_count([]))

    def test_create_employee_tour(self):
        india_company(self.env)
        employee_officer = officer(self.env, login="onboarding_employee_officer")
        # Send and Create Employee both need a hired applicant.
        applicant = hired_applicant(
            self.env,
            {
                "partner_name": "Tour Employee Candidate",
                "email_from": "tour.employee@example.test",
            },
        )
        request = receive_data(open_request(self.env, applicant))

        self.start_tour(
            f"/odoo/recruitment-applications/{applicant.id}",
            "ninthsense_onboarding_create_employee_tour",
            login=employee_officer.login,
        )

        self.assertEqual(request.state, "completed")
        self.assertEqual(request.employee_id, applicant.employee_id)
        self.assertEqual(len(applicant.employee_id), 1)
        self.assertEqual(
            self.env["hr.employee"].search_count([("name", "=", "Tour Employee Candidate")]), 1
        )

    def test_create_employee_then_edit_tour(self):
        india_company(self.env)
        employee_officer = officer(self.env, login="onboarding_edit_officer")
        applicant = hired_applicant(
            self.env,
            {"partner_name": "Tour Edit Candidate", "email_from": "tour.edit@example.test"},
        )
        request = receive_data(open_request(self.env, applicant))

        self.start_tour(
            f"/odoo/recruitment-applications/{applicant.id}",
            "ninthsense_onboarding_create_employee_edit_tour",
            login=employee_officer.login,
        )

        employee = applicant.employee_id
        self.assertEqual(employee.private_city, "Mysuru")
        self.assertEqual(employee.birthday.isoformat(), "1997-11-09")
        self.assertEqual(request.employee_id, employee)
        self.assertEqual(request.state, "completed")

    def test_cancel_on_refuse_tour(self):
        # A refuse reason with an email template would try to send mail.
        self.env["hr.applicant.refuse.reason"].search([]).write({"template_id": False})
        applicant = hired_applicant(
            self.env,
            {"partner_name": "Tour Refused Candidate", "email_from": "tour.refused@example.test"},
        )
        request, _token = send_link(self.env, applicant)

        self.start_tour(
            f"/odoo/recruitment-applications/{applicant.id}",
            "ninthsense_onboarding_cancel_on_refuse_tour",
            login=self.officer.login,
        )

        self.assertEqual(request.state, "cancelled")
        self.assertEqual(request.cancel_reason, "refused")

    def test_settings_tour(self):
        self.start_tour(
            "/odoo/action-hr_recruitment.action_hr_recruitment_configuration",
            "ninthsense_onboarding_settings_tour",
            login="admin",
        )

        params = self.env["ir.config_parameter"].sudo()
        self.assertEqual(
            params.get_str("ninthsense_onboarding.portal_url"), "https://onboarding.example.test"
        )
        self.assertEqual(params.get_str("ninthsense_onboarding.link_validity_days"), "21")
        self.assertTrue(params.get_str("ninthsense_onboarding.secret"))

    def test_template_tour(self):
        manager = new_test_user(
            self.env,
            login="onboarding_template_manager",
            groups="base.group_user,hr_recruitment.group_hr_recruitment_manager",
        )

        self.start_tour(
            "/odoo/recruitment",
            "ninthsense_onboarding_template_tour",
            login=manager.login,
        )

        standard = self.env.ref("ninthsense_onboarding.template_onboarding")
        self.assertEqual(len(standard.line_ids), 9)
        self.assertFalse(standard.line_ids[0].accept_jpg)
        foreign = self.env["ninthsense.onboarding.template"].search(
            [("name", "=", "Foreign National")]
        )
        self.assertTrue(foreign.active)
        self.assertFalse(foreign.is_default)
        self.assertTrue(standard.is_default)
        self.assertEqual(foreign.line_ids.document_type_id.mapped("code"), ["passport", "pan_card"])
        self.assertEqual(
            [
                (row.field_key, row.source_type_id.code, row.fallback_type_id.code)
                for row in foreign.mapping_ids
            ],
            [("passport_number", "passport", False)],
        )
