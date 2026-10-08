from unittest.mock import patch

from .test_create_employee import DOCUMENTS, EmployeeCase, open_request, receive_data

ACCOUNT_NUMBER = "50100247731902"


class TestEmployeeSave(EmployeeCase):
    def setUp(self):
        super().setUp()
        self.applicant = self._applicant(partner_id=self.partner.id)
        self.request = receive_data(open_request(self.env, self.applicant))

    def _create(self):
        """Click Create Employee and return the employee it saved."""
        action = self.applicant.create_employee_from_applicant()
        employee = self.applicant.employee_id
        self.assertEqual(action["res_id"], employee.id)
        return employee

    def _attachment_names(self, employee):
        return sorted(
            self.env["ir.attachment"]
            .sudo()
            .search([("res_model", "=", "hr.employee"), ("res_id", "=", employee.id)])
            .mapped("name")
        )

    def test_create_completes_the_request(self):
        employee = self._create()

        self.assertEqual(self.request.state, "completed")
        self.assertEqual(self.request.employee_id, employee)
        self.assertTrue(self.request.completed_at)
        self.assertEqual(employee.applicant_ids, self.applicant)
        self.assertEqual(employee.birthday.isoformat(), "1997-11-09")
        self.assertFalse(self.request.sudo().link_hash)
        self.assertFalse(self.applicant.onboarding_request_id)

    def test_documents_are_attached_privately(self):
        employee = self._create()

        self.assertEqual(self._attachment_names(employee), ["aadhaar_front.pdf", "pan_card.pdf"])
        copies = (
            self.env["ir.attachment"]
            .sudo()
            .search([("res_model", "=", "hr.employee"), ("res_id", "=", employee.id)])
        )
        self.assertFalse(any(copies.mapped("public")))

    def test_documents_and_applicant_attachments_are_copied_once(self):
        Attachment = self.env["ir.attachment"].sudo()
        Attachment.create(
            {
                "name": "duplicate.pdf",
                "raw": DOCUMENTS[0][1],
                "res_model": "hr.applicant",
                "res_id": self.applicant.id,
            }
        )
        Attachment.create(
            {
                "name": "cover_letter.pdf",
                "raw": b"%PDF-1.4 cover letter",
                "res_model": "hr.applicant",
                "res_id": self.applicant.id,
            }
        )

        employee = self._create()

        copies = Attachment.search(
            [("res_model", "=", "hr.employee"), ("res_id", "=", employee.id)]
        )
        self.assertEqual(
            sorted(copies.mapped("name")),
            ["cover_letter.pdf", "duplicate.pdf", "pan_card.pdf"],
        )
        self.assertEqual(len(set(copies.mapped("checksum"))), len(copies))

    def test_bank_account_is_created_on_the_work_contact(self):
        employee = self._create()

        account = employee.bank_account_ids
        self.assertEqual(len(account), 1)
        self.assertEqual(account.partner_id, employee.work_contact_id)
        self.assertEqual(account.account_number, ACCOUNT_NUMBER)
        self.assertEqual(account.bank_name, "HDFC Bank")
        self.assertEqual(account.clearing_number, "HDFC0000123")
        created = self.request.fill_line_ids.filtered(lambda line: line.outcome == "created")
        self.assertIn(ACCOUNT_NUMBER, created.mapped("value"))

    def test_without_an_indian_clearing_label_the_account_keeps_the_generic_one(self):
        Label = self.env["clearing.label"].sudo()
        Label.search([("country_id.code", "=", "IN")]).unlink()

        employee = self._create()

        account = employee.bank_account_ids
        self.assertEqual(account.clearing_number, "HDFC0000123")
        self.assertNotEqual(account.clearing_label_id.country_id.code, "IN")
        self.assertEqual(self.request.state, "completed")

    def test_an_existing_indian_clearing_label_labels_the_account(self):
        label = (
            self.env["clearing.label"]
            .sudo()
            .create({"name": "IFSC", "country_id": self.env.ref("base.in").id})
        )

        employee = self._create()

        self.assertEqual(employee.bank_account_ids.clearing_label_id, label)

    def test_existing_account_number_is_not_created_again(self):
        existing = self.env["res.partner.bank"].create(
            {"partner_id": self.partner.id, "account_number": ACCOUNT_NUMBER}
        )

        employee = self._create()

        accounts = self.env["res.partner.bank"].search(
            [("partner_id", "=", self.partner.id), ("account_number", "=", ACCOUNT_NUMBER)]
        )
        self.assertEqual(accounts, existing)
        self.assertEqual(employee.bank_account_ids, existing)
        created = self.request.fill_line_ids.filtered(lambda line: line.outcome == "created")
        self.assertNotIn(ACCOUNT_NUMBER, created.mapped("value"))

    def test_resume_lines_are_created_and_reported_after_the_fill(self):
        employee = self._create()

        education = self.env.ref("hr_skills.resume_type_education")
        experience = self.env.ref("hr_skills.resume_type_experience")
        lines = employee.resume_line_ids
        self.assertIn(
            "B.Tech, RV College of Engineering",
            lines.filtered(lambda line: line.line_type_id == education).mapped("name"),
        )
        self.assertIn(
            "Acme Corp",
            lines.filtered(lambda line: line.line_type_id == experience).mapped("name"),
        )
        report = self.request.fill_line_ids.sorted("sequence")
        outcomes = report.mapped("outcome")
        first_created = outcomes.index("created")
        self.assertTrue(first_created)
        self.assertEqual(set(outcomes[first_created:]), {"created"})
        self.assertEqual(
            set(report[first_created:].mapped("value")),
            {ACCOUNT_NUMBER, "B.Tech, RV College of Engineering", "Acme Corp"},
        )
        self.assertEqual(len(set(report.mapped("sequence"))), len(report))

    def test_a_failed_document_copy_is_reported_and_the_employee_saved(self):
        failing = self.request.document_ids.filtered(lambda d: d.code == "pan_card").attachment_id
        Attachment = self.env.registry["ir.attachment"]
        original = Attachment.copy

        def copy(records, default=None):
            if failing.id in records.ids:
                raise OSError("filestore unavailable")
            return original(records, default)

        with patch.object(Attachment, "copy", copy):
            employee = self._create()

        self.assertTrue(employee.exists())
        self.assertEqual(employee.birthday.isoformat(), "1997-11-09")
        self.assertTrue(employee.bank_account_ids)
        self.assertEqual(self.request.state, "completed")
        failed = self.request.fill_line_ids.filtered(lambda line: line.outcome == "attach_failed")
        self.assertEqual(len(failed), 1)
        pan_label = self.request.line_ids.filtered(lambda line: line.code == "pan_card").label
        self.assertEqual(failed.label, pan_label or "pan_card")
        self.assertEqual(failed.value, "pan_card.pdf")
        self.assertEqual(self._attachment_names(employee), ["aadhaar_front.pdf"])

    def test_a_deleted_resume_type_skips_its_lines_and_reports_them(self):
        self.env.ref("hr_skills.resume_type_education").sudo().unlink()

        employee = self._create()

        self.assertEqual(self.request.state, "completed")
        self.assertNotIn(
            "B.Tech, RV College of Engineering", employee.resume_line_ids.mapped("name")
        )
        self.assertIn("Acme Corp", employee.resume_line_ids.mapped("name"))
        skipped = self.request.fill_line_ids.filtered(
            lambda line: line.value == "B.Tech, RV College of Engineering"
        )
        self.assertEqual(skipped.outcome, "skipped_invalid")
        self.assertIn("resume line type", skipped.reason)
