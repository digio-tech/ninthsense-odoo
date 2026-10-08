from contextlib import closing

from odoo.addons.base.tests.common import BaseCommon
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Command
from odoo.sql_db import db_connect
from odoo.tests import new_test_user
from odoo.tools import mute_logger
from psycopg2 import IntegrityError
from psycopg2.errors import LockNotAvailable

from ..core import mapping_rules
from ..services import employee_fill
from .test_create_employee import EmployeeCase, open_request, receive_data
from .test_send import configure_portal, default_template, hired_applicant, make_template

TEMPLATE_XMLID = "ninthsense_onboarding.template_onboarding"


class TestOnboardingTemplate(BaseCommon):
    _test_user_groups = (
        "base.group_user",
        "base.group_system",
        "hr_recruitment.group_hr_recruitment_manager",
    )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(user=cls._test_user)
        configure_portal(cls.env)
        cls.template = cls.env.ref(TEMPLATE_XMLID)
        cls.officer = new_test_user(
            cls.env,
            login="template_officer",
            groups="base.group_user,hr_recruitment.group_hr_recruitment_user",
        )
        cls.manager = new_test_user(
            cls.env,
            login="template_manager",
            groups="base.group_user,hr_recruitment.group_hr_recruitment_manager",
        )

    def _document_type(self, code):
        return self.env["ninthsense.onboarding.document.type"].search([("code", "=", code)])

    def _unused_document_type(self):
        used = self.template.line_ids.document_type_id
        return self.env["ninthsense.onboarding.document.type"].search(
            [("id", "not in", used.ids)], limit=1
        )

    def test_a_template_with_no_lines_is_refused(self):
        with self.assertRaisesRegex(ValidationError, "at least one document"):
            self.template.write({"line_ids": [Command.clear()]})

    def test_a_repeated_document_type_is_refused(self):
        line = self.template.line_ids[0]
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"):
            self.template.write(
                {
                    "line_ids": [
                        Command.create(
                            {
                                "document_type_id": line.document_type_id.id,
                                "accept_pdf": True,
                                "max_mb": 3,
                            }
                        )
                    ]
                }
            )

    def test_a_line_with_no_file_type_is_refused(self):
        line = self.template.line_ids[0]
        with self.assertRaisesRegex(ValidationError, "must accept at least one file type"):
            line.write({"accept_pdf": False, "accept_jpg": False, "accept_png": False})

    def test_the_size_limit_must_be_from_1_to_20(self):
        line = self.template.line_ids[0]
        for size in (0, 21):
            with (
                self.subTest(size=size),
                self.assertRaisesRegex(ValidationError, "between 1 and 20 MB"),
            ):
                line.max_mb = size
        for size in (1, 20):
            line.max_mb = size

    def test_accept_is_computed_from_the_three_flags(self):
        line = self.template.line_ids[0]
        line.write({"accept_pdf": True, "accept_jpg": True, "accept_png": True})
        self.assertEqual(line.accept, ".pdf,.jpg,.jpeg,.png")
        line.write({"accept_jpg": False})
        self.assertEqual(line.accept, ".pdf,.png")

    def test_an_officer_can_read_but_not_write(self):
        template = self.template.with_user(self.officer)
        self.assertEqual(len(template.line_ids), len(self.template.line_ids))
        with self.assertRaises(AccessError):
            template.name = "Renamed"
        with self.assertRaises(AccessError):
            template.line_ids[0].max_mb = 5

    def test_the_template_form_opens_read_only_for_an_officer(self):
        Template = self.env["ninthsense.onboarding.template"]
        officer_arch = Template.with_user(self.officer).get_views([(False, "form")])["views"][
            "form"
        ]["arch"]
        manager_arch = Template.with_user(self.manager).get_views([(False, "form")])["views"][
            "form"
        ]["arch"]
        self.assertIn('edit="False"', officer_arch)
        self.assertNotIn('edit="False"', manager_arch)

    def test_a_manager_can_edit_the_lines(self):
        template = self.template.with_user(self.manager)
        line = template.line_ids[0]
        line.write({"max_mb": 7, "accept_jpg": False})
        template.write(
            {
                "line_ids": [
                    Command.create(
                        {
                            "document_type_id": self._unused_document_type().id,
                            "accept_pdf": True,
                            "max_mb": 3,
                        }
                    )
                ]
            }
        )
        self.assertEqual(line.max_mb, 7)
        self.assertEqual(len(template.line_ids), 10)

    def test_a_manager_creates_and_deletes_templates_and_an_officer_cannot(self):
        Template = self.env["ninthsense.onboarding.template"]
        second = make_template(Template.with_user(self.manager).env, "Fresher", ("pan_card",))
        self.assertTrue(second.active)
        self.assertFalse(second.is_default)
        with self.assertRaises(AccessError):
            make_template(Template.with_user(self.officer).env, "Officer's", ("pan_card",))
        with self.assertRaises(AccessError):
            second.with_user(self.officer).unlink()
        second.with_user(self.manager).unlink()
        self.assertFalse(second.exists())

    def test_template_names_are_unique(self):
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"):
            make_template(self.env, self.template.name, ("pan_card",))

    def test_a_new_request_gets_the_edited_lines_and_an_old_one_keeps_its_own(self):
        applicant = hired_applicant(
            self.env, {"partner_name": "Asha Rao", "email_from": "asha.template@example.test"}
        )
        applicant.action_send_onboarding_link()
        request = applicant.onboarding_request_id
        before = request.line_ids.mapped("code")

        added = self._unused_document_type()
        passport = self.template.line_ids.filtered(
            lambda line: line.document_type_id.code == "passport"
        )
        self.template.write(
            {
                "mapping_ids": [
                    Command.unlink(row.id)
                    for row in self.template.mapping_ids
                    if passport.document_type_id in row.source_type_id | row.fallback_type_id
                ],
                "line_ids": [
                    Command.unlink(passport.id),
                    Command.create(
                        {
                            "document_type_id": added.id,
                            "accept_pdf": True,
                            "max_mb": 3,
                        }
                    ),
                ],
            }
        )
        applicant.action_send_onboarding_link()
        self.assertEqual(request.line_ids.mapped("code"), before)

        other = hired_applicant(
            self.env, {"partner_name": "Ben Kumar", "email_from": "ben.template@example.test"}
        )
        other.action_send_onboarding_link()
        self.assertEqual(
            sorted(other.onboarding_request_id.line_ids.mapped("code")),
            sorted(self.template.line_ids.mapped("document_type_id.code")),
        )
        self.assertNotEqual(
            sorted(other.onboarding_request_id.line_ids.mapped("code")), sorted(before)
        )

    def test_document_types_are_read_only_for_officers_and_managers(self):
        for user in (self.officer, self.manager):
            DocumentType = self.env["ninthsense.onboarding.document.type"].with_user(user)
            with self.assertRaises(AccessError):
                DocumentType.create({"code": f"extra_{user.id}", "name": "Extra"})
            with self.assertRaises(AccessError):
                DocumentType.search([], limit=1).write({"name": "Renamed"})

    def test_a_template_with_requests_cannot_be_deleted(self):
        second = make_template(self.env, "Fresher", ("pan_card",))
        applicant = hired_applicant(
            self.env, {"partner_name": "Ravi Iyer", "email_from": "ravi.template@example.test"}
        )
        open_request(self.env, applicant, second)
        with self.assertRaisesRegex(
            UserError,
            "This template has been used for onboarding requests. Disable it instead.",
        ):
            second.with_user(self.manager).unlink()
        self.assertTrue(second.exists())

    def test_duplicating_the_default_keeps_the_original_as_the_default(self):
        copy = self.template.with_user(self.manager).copy()
        self.assertFalse(copy.is_default)
        self.assertTrue(self.template.is_default)
        self.assertEqual(len(copy.line_ids), len(self.template.line_ids))
        self.assertEqual(len(copy.mapping_ids), len(self.template.mapping_ids))
        self.assertEqual(default_template(self.env), self.template)


class TestDefaultTemplate(BaseCommon):
    _test_user_groups = ("base.group_user", "hr_recruitment.group_hr_recruitment_manager")

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(user=cls._test_user)
        cls.standard = cls.env.ref(TEMPLATE_XMLID)
        cls.second = make_template(cls.env, "Fresher", ("pan_card",))

    def test_the_installed_template_is_the_enabled_default(self):
        self.assertTrue(self.standard.active)
        self.assertTrue(self.standard.is_default)
        self.assertEqual(default_template(self.env), self.standard)
        self.assertFalse(self.second.is_default)

    def test_marking_a_template_default_clears_the_others(self):
        self.second.is_default = True
        self.assertFalse(self.standard.is_default)
        self.assertEqual(default_template(self.env), self.second)

    def test_a_disabled_template_cannot_be_the_default(self):
        with self.assertRaisesRegex(ValidationError, "disabled template cannot be the default"):
            make_template(self.env, "Archived", ("pan_card",), active=False, is_default=True)
        self.second.active = False
        with self.assertRaisesRegex(ValidationError, "disabled template cannot be the default"):
            self.second.is_default = True

    def test_the_default_cannot_be_disabled_or_deleted_while_another_is_enabled(self):
        with self.assertRaisesRegex(ValidationError, "Make another template the default"):
            self.standard.active = False
        with self.assertRaisesRegex(ValidationError, "Make another template the default"):
            self.standard.unlink()
        self.second.unlink()
        self.standard.active = False
        self.assertFalse(self.standard.is_default)

    def test_enabled_templates_need_a_default(self):
        with self.assertRaisesRegex(ValidationError, "must be the default"):
            self.standard.is_default = False
        with self.assertRaisesRegex(ValidationError, "must be the default"):
            self.standard.write({"is_default": False, "active": True})

    def test_enabling_a_template_when_none_is_enabled_makes_it_the_default(self):
        self.second.action_archive()
        self.standard.action_archive()
        self.assertFalse(self.standard.is_default)
        self.second.action_unarchive()
        self.assertTrue(self.second.is_default)
        self.assertEqual(default_template(self.env), self.second)
        self.standard.action_unarchive()
        self.assertFalse(self.standard.is_default)
        self.assertEqual(default_template(self.env), self.second)

    def test_the_first_template_created_when_none_is_enabled_becomes_the_default(self):
        self.second.unlink()
        self.standard.active = False
        third = make_template(self.env, "Intern", ("pan_card",))
        self.assertTrue(third.is_default)
        fourth = make_template(self.env, "Contractor", ("pan_card",))
        self.assertFalse(fourth.is_default)

    def test_two_defaults_are_refused_by_the_database(self):
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"):
            self.env.cr.execute(
                "UPDATE ninthsense_onboarding_template SET is_default = TRUE WHERE id = %s",
                [self.second.id],
            )

    def test_changing_which_templates_are_enabled_locks_every_template(self):
        self.second.active = False
        with (
            closing(db_connect(self.env.cr.dbname).cursor()) as other,
            self.assertRaises(LockNotAvailable),
            mute_logger("odoo.sql_db"),
        ):
            other.execute(
                "SELECT id FROM ninthsense_onboarding_template WHERE id = %s FOR UPDATE NOWAIT",
                [self.standard.id],
            )

    def test_disabling_another_template_keeps_the_default(self):
        self.second.active = False
        self.assertTrue(self.standard.is_default)


class TestTemplateMapping(BaseCommon):
    _test_user_groups = ("base.group_user", "hr_recruitment.group_hr_recruitment_manager")

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(user=cls._test_user)
        cls.standard = cls.env.ref(TEMPLATE_XMLID)
        cls.template = make_template(
            cls.env,
            "Foreign National",
            ("passport", "pan_card", "resume"),
            [("date_of_birth", "passport", "pan_card")],
        )

    def _type(self, code):
        return self.env["ninthsense.onboarding.document.type"].search([("code", "=", code)])

    def _add_row(self, key, source, fallback=None):
        self.template.write(
            {
                "mapping_ids": [
                    Command.create(
                        {
                            "field_key": key,
                            "source_type_id": self._type(source).id,
                            "fallback_type_id": self._type(fallback).id if fallback else False,
                        }
                    )
                ]
            }
        )

    def test_the_seeded_mapping_follows_the_rules_and_covers_every_suppliable_key(self):
        codes = self.standard.line_ids.document_type_id.mapped("code")
        rows = [
            (row.field_key, row.source_type_id.code, row.fallback_type_id.code or None)
            for row in self.standard.mapping_ids
        ]
        self.assertEqual(mapping_rules.mapping_problems(rows, codes), [])
        self.assertEqual(sorted(rows), sorted(mapping_rules.default_rows(codes)))
        self.assertIn(("date_of_birth", "aadhaar_front", "pan_card"), rows)

    def test_a_template_with_no_mapping_is_allowed(self):
        empty = make_template(self.env, "Documents Only", ("pan_card",))
        self.assertFalse(empty.mapping_ids)

    def test_the_field_dropdown_shows_section_and_label(self):
        labels = dict(
            self.env["ninthsense.onboarding.template.mapping"]._fields["field_key"].selection
        )
        self.assertEqual(labels["date_of_birth"], "Personal Information: Date of Birth")
        self.assertEqual(labels["bank_ac_no"], "Banking: Bank Account Number")
        self.assertEqual(labels["education.institution"], "Education: Institution")
        self.assertEqual(labels["external_work_history.employer"], "Employment: Previous Employer")

    def test_the_document_dropdowns_offer_only_the_template_documents_that_supply_the_key(self):
        row = self.template.mapping_ids
        self.assertEqual(
            set(row.allowed_type_ids.mapped("code")), {"passport", "pan_card", "resume"}
        )
        row.write({"field_key": "passport_number", "fallback_type_id": False})
        self.assertEqual(row.allowed_type_ids.mapped("code"), ["passport"])
        self.assertEqual(row._fields["source_type_id"].domain, "[('id', 'in', allowed_type_ids)]")
        self.assertEqual(row._fields["fallback_type_id"].domain, "[('id', 'in', allowed_type_ids)]")

    def test_a_field_mapped_twice_is_refused(self):
        with self.assertRaisesRegex(
            ValidationError, "Personal Information: Date of Birth is mapped more than once"
        ):
            self._add_row("date_of_birth", "pan_card")

    def test_a_source_that_cannot_supply_the_field_is_refused(self):
        with self.assertRaisesRegex(
            ValidationError, "Statutory: Passport Number: the source document must be one of"
        ):
            self._add_row("passport_number", "pan_card")

    def test_a_source_not_in_the_template_is_refused(self):
        with self.assertRaisesRegex(
            ValidationError, "Personal Information: Legal Name: the source document must be one of"
        ):
            self._add_row("legal_name", "aadhaar_front")

    def test_a_fallback_not_allowed_is_refused(self):
        with self.assertRaisesRegex(
            ValidationError,
            "Personal Information: Legal Name: the fallback document must be one of",
        ):
            self._add_row("legal_name", "passport", "aadhaar_front")

    def test_a_fallback_equal_to_the_source_is_refused(self):
        with self.assertRaisesRegex(
            ValidationError,
            "Personal Information: Date of Birth: the fallback document must differ",
        ):
            self.template.mapping_ids.fallback_type_id = self._type("passport")

    def test_removing_a_document_that_feeds_a_row_is_refused_naming_the_field(self):
        passport = self.template.line_ids.filtered(
            lambda line: line.document_type_id.code == "passport"
        )
        with self.assertRaisesRegex(ValidationError, "Personal Information: Date of Birth"):
            self.template.write({"line_ids": [Command.unlink(passport.id)]})
        with self.assertRaisesRegex(ValidationError, "Personal Information: Date of Birth"):
            passport.unlink()

    def test_a_document_and_its_rows_can_be_removed_in_one_save(self):
        passport = self.template.line_ids.filtered(
            lambda line: line.document_type_id.code == "passport"
        )
        self.template.write(
            {
                "line_ids": [Command.unlink(passport.id)],
                "mapping_ids": [Command.clear()],
            }
        )
        self.assertNotIn("passport", self.template.line_ids.document_type_id.mapped("code"))

    def test_a_new_template_with_documents_and_mapping_saves_in_one_go(self):
        template = make_template(
            self.env,
            "Fresher",
            ("aadhaar_front", "pan_card"),
            [("legal_name", "aadhaar_front", "pan_card"), ("sex", "aadhaar_front", None)],
        )
        self.assertEqual(len(template.mapping_ids), 2)


class TestTemplateRulesHoldOverRpc(BaseCommon):
    _test_user_groups = ("base.group_user", "hr_recruitment.group_hr_recruitment_manager")

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(user=cls._test_user)
        cls.standard = cls.env.ref(TEMPLATE_XMLID)
        cls.pan_only = make_template(cls.env, "PAN Only", ("pan_card",))

    def _standard_row(self, key):
        return self.standard.mapping_ids.filtered(lambda row: row.field_key == key)

    def test_a_client_cannot_skip_the_mapping_check_through_the_context(self):
        row = self._standard_row("passport_number")
        pan = self.pan_only.line_ids.document_type_id
        with self.assertRaisesRegex(ValidationError, "Passport Number: the source document"):
            row.with_context(ninthsense_template_saving=True).write({"source_type_id": pan.id})
        with self.assertRaisesRegex(ValidationError, "at least one document"):
            self.pan_only.line_ids.with_context(ninthsense_template_saving=True).unlink()

    def test_moving_a_mapping_row_to_a_template_without_its_document_is_refused(self):
        row = self._standard_row("passport_number")
        with self.assertRaisesRegex(ValidationError, "Passport Number: the source document"):
            row.template_id = self.pan_only

    def test_moving_a_line_that_feeds_mapping_rows_is_refused(self):
        passport = self.standard.line_ids.filtered(
            lambda line: line.document_type_id.code == "passport"
        )
        with self.assertRaisesRegex(ValidationError, "Passport Number: the source document"):
            passport.template_id = self.pan_only

    def test_moving_a_template_s_last_line_away_is_refused(self):
        with self.assertRaisesRegex(ValidationError, "at least one document"):
            self.pan_only.line_ids.template_id = make_template(
                self.env, "Other", ("aadhaar_front",)
            )

    def test_a_template_created_with_no_documents_is_refused(self):
        with self.assertRaisesRegex(ValidationError, "at least one document"):
            self.env["ninthsense.onboarding.template"].create({"name": "Empty"})

    def test_deleting_the_last_line_directly_is_refused(self):
        with self.assertRaisesRegex(ValidationError, "at least one document"):
            self.pan_only.line_ids.unlink()
        self.assertTrue(self.pan_only.line_ids)


class TestTemplateMappingFill(EmployeeCase):
    def setUp(self):
        super().setUp()
        self.template = make_template(
            self.env(su=True),
            "Foreign National",
            ("passport", "pan_card"),
            [("date_of_birth", "passport", "pan_card")],
        )
        self.applicant = self._applicant()
        self.request = receive_data(
            open_request(self.env, self.applicant, self.template),
            values={
                ("date_of_birth", "passport"): "1990-04-02",
                ("date_of_birth", "pan_card"): "1990-04-03",
                ("passport_number", "passport"): "N1234567",
            },
            documents=(),
        )

    def _employee(self):
        self.applicant.create_employee_from_applicant()
        return self.applicant.employee_id

    def test_the_request_asks_only_for_its_template_documents(self):
        self.assertEqual(self.request.line_ids.mapped("code"), ["passport", "pan_card"])

    def test_the_birthday_comes_from_the_passport(self):
        employee = self._employee()
        self.assertEqual(employee.birthday.isoformat(), "1990-04-02")
        self.assertFalse(employee.passport_id)
        labels = self.request.fill_line_ids.mapped("label")
        self.assertEqual(labels, ["Date of Birth"])

    def test_an_edited_mapping_changes_the_fill(self):
        row = self.template.mapping_ids
        row.write(
            {
                "source_type_id": row.fallback_type_id.id,
                "fallback_type_id": row.source_type_id.id,
            }
        )
        self.assertEqual(self._employee().birthday.isoformat(), "1990-04-03")
        self.assertEqual(self.request.line_ids.mapped("code"), ["passport", "pan_card"])

    def test_the_fallback_is_used_when_the_source_has_no_value(self):
        self.request.sudo().value_ids.filtered(
            lambda value: value.field_key == "date_of_birth" and value.source_code == "passport"
        ).unlink()
        self.assertEqual(self._employee().birthday.isoformat(), "1990-04-03")

    def test_a_request_without_a_template_fills_nothing(self):
        self.request.sudo().template_id = False
        self.assertEqual(employee_fill.chosen_values(self.request), {})
        self.assertFalse(self._employee().birthday)
