from unittest.mock import patch

from odoo import api, fields
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, new_test_user

from ..services import config as ns_config
from ..services import invitations, storage
from .test_send import configure_portal, default_template, hired_applicant

OFFICER_GROUPS = "base.group_user,hr.group_hr_user,hr_recruitment.group_hr_recruitment_user"
PARTNER_PHONE = "+91 80 4000 1234"
ADDRESS = "14 Nandi Durga Road, Benson Town, Bengaluru, Karnataka 560046"
VALUES = {
    "legal_name": "Priya Raghavan",
    "sex": "female",
    "date_of_birth": "1997-11-09",
    "cell_number": "9845012345",
    "personal_email": "priya.personal@example.test",
    "current_address": ADDRESS,
    "aadhaar_number": "XXXX XXXX 0123",
    "bank_ac_no": "50100247731902",
    "bank_name": "HDFC Bank",
    "ifsc_code": "HDFC0000123",
    "education.degree": "B.Tech",
    "education.institution": "RV College of Engineering",
    "education.year": "2019",
    "external_work_history.employer": "Acme Corp",
    "external_work_history.designation": "Engineer",
}
DOCUMENTS = (
    ("aadhaar_front", b"%PDF-1.4 aadhaar front"),
    ("pan_card", b"%PDF-1.4 pan card"),
)


def officer(env, login="onb_employee_officer"):
    return new_test_user(env, login=login, groups=OFFICER_GROUPS)


def open_request(env, applicant, template=None):
    """Send the link the way the button does and return the request."""
    configure_portal(env)
    template = template or default_template(env)
    request, _url = invitations.send(
        applicant, ns_config.load(env), template, fields.Datetime.now()
    )
    return request


def receive_data(request, values=VALUES, documents=DOCUMENTS):
    """Store documents and parsed values on the request as a delivery would.

    A value given by key alone is read from the document its template's
    mapping names as the source. A `(key, code)` pair names the document.
    """
    request = request.sudo()
    now = fields.Datetime.now()
    for code, content in documents:
        storage.store_document(
            request, code, f"doc_{code}", f"{code}.pdf", content, "application/pdf", now
        )
    sources = {row.field_key: row.source_type_id.code for row in request.template_id.mapping_ids}
    rows = []
    for key, value in values.items():
        key, code = key if isinstance(key, tuple) else (key, sources.get(key))
        rows.append(
            {
                "request_id": request.id,
                "field_key": key,
                "label": key,
                "value": value,
                "source_code": code,
            }
        )
    request.env["ninthsense.onboarding.value"].create(rows)
    request.write({"state": "data_received", "received_at": now})
    return request


def india_company(env):
    env.company.sudo().country_id = env.ref("base.in")


class EmployeeCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        india_company(cls.env)
        configure_portal(cls.env)
        cls.user = officer(cls.env)
        cls.env = cls.env(user=cls.user)
        cls.partner = cls.env["res.partner"].create(
            {"name": "Priya Raghavan", "email": "priya@example.test", "phone": PARTNER_PHONE}
        )

    def _applicant(self, name="Priya Raghavan", **extra):
        values = {"partner_name": name, "email_from": "priya@example.test"}
        values.update(extra)
        return hired_applicant(self.env, values)

    def _counts(self):
        env = self.env(su=True)
        return (
            env["hr.employee"].search_count([]),
            env["res.partner.bank"].search_count([]),
            env["hr.resume.line"].search_count([]),
        )


class TestCreateEmployee(EmployeeCase):
    def test_data_received_saves_a_filled_employee(self):
        applicant = self._applicant(partner_id=self.partner.id)
        request = receive_data(open_request(self.env, applicant))
        employees, accounts, resume_lines = self._counts()

        action = applicant.create_employee_from_applicant()

        employee = applicant.employee_id
        self.assertEqual(len(employee), 1)
        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertEqual(action["res_model"], "hr.employee")
        self.assertEqual(action["res_id"], employee.id)
        self.assertEqual(self._counts()[0], employees + 1)
        self.assertEqual(self._counts()[1], accounts + 1)
        self.assertGreater(self._counts()[2], resume_lines)

        # Odoo's own values are kept.
        self.assertEqual(employee.name, "Priya Raghavan")
        self.assertEqual(employee.legal_name, "Priya Raghavan")
        self.assertEqual(employee.private_phone, PARTNER_PHONE)
        self.assertEqual(employee.private_email, "priya@example.test")
        self.assertEqual(employee.work_contact_id, self.partner)
        self.assertEqual(employee.applicant_ids, applicant)
        # The empty mapped fields are filled.
        self.assertEqual(employee.birthday.isoformat(), "1997-11-09")
        self.assertEqual(employee.sex, "female")
        self.assertEqual(employee.identification_id, "XXXX XXXX 0123")
        self.assertEqual(employee.private_city, "Bengaluru")
        self.assertEqual(employee.private_zip, "560046")
        self.assertEqual(employee.private_state_id, self.env.ref("base.state_in_ka"))

        self.assertEqual(request.state, "completed")
        self.assertEqual(request.employee_id, employee)
        self.assertTrue(request.completed_at)
        self.assertTrue(request.filled_at)
        self.assertFalse(request.sudo().link_hash)
        by_label = {line.label: line for line in request.fill_line_ids}
        self.assertEqual(by_label["Date of Birth"].outcome, "filled")
        self.assertEqual(by_label["Mobile"].outcome, "skipped_different")
        self.assertEqual(by_label["Mobile"].current_value, PARTNER_PHONE)
        self.assertEqual(by_label["Personal Email"].outcome, "skipped_different")
        self.assertEqual(by_label["Aadhaar Number"].value, "XXXX XXXX 0123")
        self.assertNotIn("Legal Name", by_label)

    def test_link_sent_without_data_is_native_and_leaves_the_request(self):
        applicant = self._applicant()
        request = open_request(self.env, applicant)
        link_hash = request.sudo().link_hash

        action = applicant.create_employee_from_applicant()

        employee = applicant.employee_id
        self.assertEqual(action["res_id"], employee.id)
        self.assertEqual(employee.name, "Priya Raghavan")
        self.assertFalse(employee.birthday)
        self.assertFalse(employee.bank_account_ids)
        self.assertEqual(request.state, "link_sent")
        self.assertFalse(request.employee_id)
        self.assertFalse(request.fill_line_ids)
        self.assertFalse(request.filled_at)
        self.assertEqual(request.sudo().link_hash, link_hash)

    def test_no_open_request_is_native(self):
        applicant = self._applicant()

        action = applicant.create_employee_from_applicant()

        self.assertTrue(applicant.employee_id)
        self.assertEqual(action["res_id"], applicant.employee_id.id)

    def test_linked_employee_never_gets_a_second_one(self):
        applicant = self._applicant()
        applicant.create_employee_from_applicant()
        employee = applicant.employee_id
        # Sending refuses an applicant with an employee, so the request is made directly.
        request = receive_data(
            self.env["ninthsense.onboarding.request"]
            .sudo()
            .create({"company_id": self.env.company.id, "applicant_id": applicant.id})
        )
        before = self._counts()

        action = applicant.create_employee_from_applicant()

        self.assertEqual(self._counts(), before)
        self.assertEqual(action["res_id"], employee.id)
        self.assertEqual(applicant.employee_id, employee)
        self.assertEqual(request.state, "data_received")

    def test_applicant_without_partner_gets_one(self):
        applicant = self._applicant(name="Kiran Das", email_from="kiran@example.test")
        request = receive_data(open_request(self.env, applicant))
        applicant.partner_id = False

        applicant.create_employee_from_applicant()

        self.assertEqual(applicant.partner_id.name, "Kiran Das")
        self.assertEqual(applicant.partner_id.email, "kiran@example.test")
        self.assertEqual(applicant.employee_id.work_contact_id, applicant.partner_id)
        self.assertEqual(request.state, "completed")

    def test_a_failed_create_leaves_nothing_and_can_be_repeated(self):
        applicant = self._applicant(partner_id=self.partner.id)
        request = receive_data(open_request(self.env, applicant))
        link_hash = request.sudo().link_hash
        before = self._counts()
        Employee = self.env.registry["hr.employee"]
        original = Employee.create

        @api.model_create_multi
        def create(model, vals_list):
            original(model, vals_list)
            raise ValidationError("forced")

        with patch.object(Employee, "create", create), self.assertRaises(ValidationError):
            applicant.create_employee_from_applicant()

        self.assertEqual(self._counts(), before)
        self.assertFalse(applicant.employee_id)
        self.assertEqual(request.state, "data_received")
        self.assertFalse(request.employee_id)
        self.assertFalse(request.fill_line_ids)
        self.assertEqual(request.sudo().link_hash, link_hash)
        self.assertTrue(request.value_ids)

        applicant.create_employee_from_applicant()

        self.assertTrue(applicant.employee_id)
        self.assertEqual(request.state, "completed")
