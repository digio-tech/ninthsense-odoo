from odoo.addons.base.tests.common import BaseCommon
from odoo.fields import Command
from odoo.tools import convert_file, mute_logger
from psycopg2 import IntegrityError

from .test_send import configure_portal, hired_applicant, make_template

MODULE = "ninthsense_onboarding"


def _line(template, code):
    return template.line_ids.filtered(lambda line: line.document_type_id.code == code)


class TestDataReloadKeepsHrEdits(BaseCommon):
    _test_user_groups = (
        "base.group_user",
        "base.group_system",
        "hr_recruitment.group_hr_recruitment_manager",
    )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = cls._test_user

    def _reload(self, path):
        convert_file(
            self.env(user=self.admin),
            MODULE,
            path,
            {},
            mode="update",
            noupdate=False,
        )

    def test_reloading_the_data_files_keeps_edits(self):
        template = self.env.ref(f"{MODULE}.template_onboarding")
        line = _line(template, "aadhaar_front")
        mail_template = self.env.ref(f"{MODULE}.mail_template_onboarding_link")
        line.write({"max_mb": 9, "accept_jpg": False})
        template.name = "Edited by HR"
        mapping = template.mapping_ids.filtered(lambda row: row.field_key == "date_of_birth")
        mapping.fallback_type_id = False
        mail_template.body_html = "<p>Edited by HR</p>"

        self._reload("data/template_data.xml")
        self._reload("data/mail_template_data.xml")

        self.assertEqual(line.max_mb, 9)
        self.assertFalse(line.accept_jpg)
        self.assertEqual(template.name, "Edited by HR")
        self.assertEqual(len(template.line_ids), 9)
        self.assertTrue(template.is_default)
        self.assertFalse(mapping.fallback_type_id)
        self.assertEqual(mail_template.body_html, "<p>Edited by HR</p>")

    def test_a_deleted_line_and_its_mapping_stay_deleted_and_send_still_works(self):
        template = self.env.ref(f"{MODULE}.template_onboarding")
        line = _line(template, "passport")
        passport = line.document_type_id
        passport_rows = template.mapping_ids.filtered(
            lambda row: passport in row.source_type_id | row.fallback_type_id
        )
        self.assertTrue(passport_rows)
        mapping_count = len(template.mapping_ids) - len(passport_rows)
        passport_rows.unlink()
        line.unlink()
        template.write(
            {
                "line_ids": [
                    Command.create(
                        {"document_type_id": passport.id, "accept_pdf": True, "max_mb": 5}
                    )
                ]
            }
        )

        self._reload("data/template_data.xml")

        passport_lines = template.line_ids.filtered(lambda line: line.document_type_id == passport)
        self.assertEqual(len(passport_lines), 1)
        self.assertEqual(passport_lines.max_mb, 5)
        self.assertEqual(len(template.line_ids), 9)
        self.assertEqual(len(template.mapping_ids), mapping_count)

        configure_portal(self.env)
        applicant = hired_applicant(
            self.env, {"partner_name": "Asha Rao", "email_from": "asha.upgrade@example.test"}
        )
        applicant.with_user(self.admin).action_send_onboarding_link()
        request = applicant.onboarding_request_id
        self.assertEqual(request.line_ids.filtered(lambda line: line.code == "passport").max_mb, 5)

    def test_a_document_type_cannot_be_listed_twice_on_a_line_write(self):
        template = self.env.ref(f"{MODULE}.template_onboarding")
        lines = template.line_ids
        template.mapping_ids.filtered(
            lambda row: lines[1].document_type_id in row.source_type_id | row.fallback_type_id
        ).unlink()
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"):
            lines[1].document_type_id = lines[0].document_type_id
            lines.flush_recordset()

    def test_a_deleted_installed_template_is_not_recreated(self):
        template = self.env.ref(f"{MODULE}.template_onboarding")
        mine = make_template(self.env, "Mine", ("pan_card",), is_default=True)
        template.unlink()

        self._reload("data/template_data.xml")

        Template = self.env["ninthsense.onboarding.template"].with_context(active_test=False)
        self.assertFalse(self.env.ref(f"{MODULE}.template_onboarding", raise_if_not_found=False))
        self.assertEqual(Template.search([]), mine)
        self.assertTrue(mine.is_default)
