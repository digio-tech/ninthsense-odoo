from odoo.addons.base.tests.common import BaseCommon
from odoo.exceptions import AccessError
from odoo.fields import Command
from odoo.tests import new_test_user

from .test_create_employee import receive_data
from .test_send import configure_portal, hired_applicant

CHILD_MODELS = (
    "ninthsense.onboarding.value",
    "ninthsense.onboarding.document",
    "ninthsense.onboarding.request.line",
    "ninthsense.onboarding.fill.line",
)

RECRUITER_GROUPS = "base.group_user,hr_recruitment.group_hr_recruitment_user"


class TestMultiCompany(BaseCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        configure_portal(cls.env)
        cls.company_a = cls.env.company
        cls.company_b = cls.env["res.company"].create({"name": "Onboarding Company B"})
        cls.user_a = new_test_user(
            cls.env,
            login="onb_user_a",
            groups=RECRUITER_GROUPS,
            company_id=cls.company_a.id,
            company_ids=[Command.set(cls.company_a.ids)],
        )
        cls.user_b = new_test_user(
            cls.env,
            login="onb_user_b",
            groups=RECRUITER_GROUPS,
            company_id=cls.company_b.id,
            company_ids=[Command.set(cls.company_b.ids)],
        )
        applicant = hired_applicant(
            cls.env["hr.applicant"].with_company(cls.company_b).env,
            {
                "partner_name": "Kiran Das",
                "email_from": "kiran.company@example.test",
                "company_id": cls.company_b.id,
            },
        )
        applicant.with_user(cls.user_b).with_context(
            allowed_company_ids=cls.company_b.ids
        ).action_send_onboarding_link()
        cls.request_id = (
            cls.env["ninthsense.onboarding.request"]
            .sudo()
            .search([("applicant_id", "=", applicant.id)])
        ).id

    def _request(self):
        return self.env["ninthsense.onboarding.request"].sudo().browse(self.request_id)

    def test_a_request_of_company_b_is_invisible_to_a_user_of_company_a_only(self):
        self.assertEqual(self._request().company_id, self.company_b)
        domain = [("id", "=", self._request().id)]
        Request = self.env["ninthsense.onboarding.request"]

        self.assertEqual(
            Request.with_user(self.user_b)
            .with_context(allowed_company_ids=self.company_b.ids)
            .search(domain),
            self._request(),
        )
        self.assertFalse(
            Request.with_user(self.user_a)
            .with_context(allowed_company_ids=self.company_a.ids)
            .search(domain)
        )
        with self.assertRaises(AccessError):
            self._request().with_user(self.user_a).with_context(
                allowed_company_ids=self.company_a.ids
            ).read(["state"])
        with self.assertRaises(AccessError):
            self._request().with_user(self.user_a).with_context(
                allowed_company_ids=self.company_a.ids
            ).write({"candidate_email": "x@example.test"})

    def test_the_data_of_a_company_b_request_is_invisible_to_a_user_of_company_a_only(self):
        request = receive_data(self._request())
        self.env["ninthsense.onboarding.fill.line"].sudo().create(
            {"request_id": request.id, "outcome": "filled", "label": "PAN", "value": "x"}
        )
        for name in CHILD_MODELS:
            with self.subTest(model=name):
                domain = [("request_id", "=", request.id)]
                Model = self.env[name]
                self.assertTrue(Model.sudo().search(domain))
                self.assertTrue(
                    Model.with_user(self.user_b)
                    .with_context(allowed_company_ids=self.company_b.ids)
                    .search(domain)
                )
                as_a = Model.with_user(self.user_a).with_context(
                    allowed_company_ids=self.company_a.ids
                )
                self.assertFalse(as_a.search(domain))
                self.assertFalse(as_a.search([]) & Model.sudo().search(domain))
                with self.assertRaises(AccessError):
                    Model.sudo().search(domain, limit=1).with_user(self.user_a).with_context(
                        allowed_company_ids=self.company_a.ids
                    ).read(["request_id"])
