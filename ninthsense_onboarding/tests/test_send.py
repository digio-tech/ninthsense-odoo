from unittest.mock import patch

from odoo import fields
from odoo.addons.base.tests.common import BaseCommon
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import Form
from odoo.tools import config as odoo_config

from ..core.links import hash_token
from ..services import config as ns_config
from ..services import invitations

PORTAL_URL = "https://portal.example.test"
SECRET = "s" * 40


HIRED_STAGE_XMLID = "hr_recruitment.stage_job5"
LINK_DIALOG = "ninthsense.onboarding.link.dialog"
NO_MAIL_SERVER_WARNING = (
    "No outgoing mail server is configured, so the email will not be delivered. "
    "Copy the link and send it to the candidate yourself."
)


def configure_portal(env):
    params = env["ir.config_parameter"].sudo()
    params.set_str("ninthsense_onboarding.portal_url", PORTAL_URL)
    params.set_str("ninthsense_onboarding.secret", SECRET)


def hired_applicant(env, values):
    """An applicant in a hired stage, the only kind Send accepts."""
    return env["hr.applicant"].create(dict(values, stage_id=env.ref(HIRED_STAGE_XMLID).id))


def default_template(env):
    return env["ninthsense.onboarding.template"].search([("is_default", "=", True)], limit=1)


def document_type(env, code):
    return env["ninthsense.onboarding.document.type"].search([("code", "=", code)])


def make_template(env, name, codes, mapping=(), **values):
    """A template asking for `codes`, PDF only, with `(key, source, fallback)` mapping rows."""
    lines = [
        Command.create(
            {
                "sequence": index,
                "document_type_id": document_type(env, code).id,
                "mandatory": True,
                "accept_pdf": True,
                "max_mb": 3,
            }
        )
        for index, code in enumerate(codes)
    ]
    rows = [
        Command.create(
            {
                "field_key": key,
                "source_type_id": document_type(env, source).id,
                "fallback_type_id": document_type(env, fallback).id if fallback else False,
            }
        )
        for key, source, fallback in mapping
    ]
    return env["ninthsense.onboarding.template"].create(
        dict(values, name=name, line_ids=lines, mapping_ids=rows)
    )


class TestSendLink(BaseCommon):
    _test_user_groups = ("base.group_user", "hr_recruitment.group_hr_recruitment_user")

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        configure_portal(cls.env)
        cls.env = cls.env(user=cls._test_user)
        cls.Request = cls.env["ninthsense.onboarding.request"]
        cls.applicant = hired_applicant(
            cls.env, {"partner_name": "Asha Rao", "email_from": "asha@example.com"}
        )
        cls.standard = default_template(cls.env)

    def _requests(self, applicant=None):
        return self.Request.search([("applicant_id", "=", (applicant or self.applicant).id)])

    def _token_in(self, mail):
        marker = f"{PORTAL_URL}/s/"
        start = mail.body_html.index(marker) + len(marker)
        end = start
        while mail.body_html[end] not in "\"'<& ":
            end += 1
        return mail.body_html[start:end]

    def _no_mail_server(self, smtp_server="localhost"):
        """No `ir.mail_server` record and Odoo's own SMTP setting left at `smtp_server`."""
        self.env["ir.mail_server"].sudo().search([]).unlink()
        patcher = patch.dict(odoo_config.options, {"smtp_server": smtp_server})
        patcher.start()
        self.addCleanup(patcher.stop)

    def _assert_link_dialog(self, action, request):
        """`action` opens the link dialog for `request`'s current link, and stores nothing."""
        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertEqual(action["res_model"], LINK_DIALOG)
        self.assertEqual(action["target"], "new")
        self.assertNotIn("res_id", action)
        context = action["context"]
        self.assertEqual(context["default_email"], request.candidate_email)
        url = context["default_url"]
        self.assertTrue(url.startswith(f"{PORTAL_URL}/s/"))
        self.assertEqual(request.sudo().link_hash, hash_token(url.removeprefix(f"{PORTAL_URL}/s/")))
        self.assertIn(url, request.invite_mail_id.sudo().body_html)
        dialog = Form(self.env[LINK_DIALOG].with_context(**context))
        self.assertEqual(dialog.url, url)
        self.assertEqual(dialog.message, f"Onboarding link sent to {request.candidate_email}")
        self.assertFalse(self.env[LINK_DIALOG].sudo().search_count([]))
        return dialog

    def _second_template(self, **values):
        return make_template(
            self.env(su=True),
            "Foreign National",
            ("passport", "pan_card"),
            [("date_of_birth", "passport", "pan_card")],
            **values,
        ).with_env(self.env)

    def test_send_creates_request_and_queues_email(self):
        template = self.standard
        action = self.applicant.action_send_onboarding_link()

        request = self._requests()
        self.assertEqual(len(request), 1)
        self.assertEqual(request.state, "link_sent")
        self.assertEqual(request.candidate_email, "asha@example.com")
        self.assertEqual(request.applicant_ref, self.applicant.id)
        self.assertEqual(request.template_id, template)
        self.assertEqual(len(request.line_ids), len(template.line_ids))
        self.assertTrue(request.line_ids)
        self.assertTrue(request.link_expires_at)

        mail = request.invite_mail_id.sudo()
        self.assertEqual(len(mail), 1)
        self.assertIn("asha@example.com", mail.email_to)
        token = self._token_in(mail)
        self.assertEqual(request.sudo().link_hash, hash_token(token))
        self.assertEqual(request.invite_state, "queued")

        self._assert_link_dialog(action, request)

    def test_resend_keeps_one_request_and_its_lines(self):
        self.applicant.action_send_onboarding_link()
        request = self._requests()
        first_hash = request.sudo().link_hash
        lines = request.line_ids
        self.standard.sudo().line_ids[:1].max_mb = 9

        self.applicant.email_from = "asha.new@example.com"
        action = self.applicant.action_send_onboarding_link()

        self.assertEqual(self._requests(), request)
        dialog = self._assert_link_dialog(action, request)
        self.assertEqual(dialog.email, "asha.new@example.com")
        self.assertNotEqual(request.sudo().link_hash, first_hash)
        self.assertEqual(request.candidate_email, "asha.new@example.com")
        self.assertIn("asha.new@example.com", request.invite_mail_id.sudo().email_to)
        self.assertEqual(request.line_ids, lines)
        self.assertEqual(set(request.line_ids.mapped("max_mb")), {3})

    def test_no_email_is_refused(self):
        applicant = hired_applicant(self.env, {"partner_name": "No Mail"})
        with self.assertRaisesRegex(UserError, "has no email address"):
            applicant.action_send_onboarding_link()
        self.assertFalse(self._requests(applicant))

    def test_missing_settings_are_refused(self):
        self.env["ir.config_parameter"].sudo().set_str("ninthsense_onboarding.secret", "")
        with self.assertRaisesRegex(UserError, "not set up yet"):
            self.applicant.action_send_onboarding_link()
        self.assertFalse(self._requests())

    def test_failed_queueing_leaves_nothing_behind(self):
        with (
            patch(
                "odoo.addons.mail.models.mail_template.MailTemplate.send_mail",
                side_effect=ValueError("boom"),
            ),
            self.assertRaisesRegex(UserError, "Nothing was sent"),
            self.cr.savepoint(),
        ):
            self.applicant.action_send_onboarding_link()
        self.assertFalse(self._requests())
        self.assertFalse(self.Request.sudo().search([("link_hash", "!=", False)]))

    def test_resend_from_data_received_keeps_values(self):
        self.applicant.action_send_onboarding_link()
        request = self._requests()
        value = (
            self.env["ninthsense.onboarding.value"]
            .sudo()
            .create({"request_id": request.id, "field_key": "pan_number", "value": "ABCDE1234F"})
        )
        request.sudo().state = "data_received"

        self.applicant.action_send_onboarding_link()

        self.assertEqual(self._requests(), request)
        self.assertEqual(request.state, "link_sent")
        self.assertEqual(request.value_ids, value)

    def test_an_archived_unhired_applicant_or_one_with_an_employee_is_refused(self):
        template = self.standard
        config = ns_config.load(self.env)
        archived = hired_applicant(
            self.env, {"partner_name": "Gone", "email_from": "gone@example.com"}
        )
        archived.action_archive()
        hired = hired_applicant(
            self.env(su=True), {"partner_name": "Hired", "email_from": "hired@example.com"}
        )
        hired.employee_id = self.env["hr.employee"].sudo().create({"name": "Hired"})
        not_hired = self.env["hr.applicant"].create(
            {"partner_name": "Not Yet", "email_from": "not.yet@example.com"}
        )

        for applicant, message in (
            (archived, "is archived"),
            (hired, "already has an employee"),
            (not_hired, "is not hired yet"),
        ):
            with self.subTest(message), self.assertRaisesRegex(UserError, message):
                invitations.send(
                    applicant.with_env(self.env), config, template, fields.Datetime.now()
                )
            self.assertFalse(self.Request.sudo().search([("applicant_id", "=", applicant.id)]))

    def test_the_button_shows_only_for_a_hired_applicant(self):
        arch = self.env["hr.applicant"].get_views([(False, "form")])["views"]["form"]["arch"]
        self.assertIn(
            'invisible="not active or employee_id or not date_closed or onboarding_request_id"',
            arch,
        )
        not_hired = self.env["hr.applicant"].create(
            {"partner_name": "Not Yet", "email_from": "not.yet@example.com"}
        )
        self.assertFalse(not_hired.date_closed)
        self._second_template()
        with self.assertRaisesRegex(UserError, "is not hired yet"):
            not_hired.action_send_onboarding_link()
        self.assertFalse(self._requests(not_hired))

    def test_one_enabled_template_sends_directly(self):
        self._second_template(active=False)

        action = self.applicant.action_send_onboarding_link()

        self._assert_link_dialog(action, self._requests())
        self.assertEqual(self._requests().template_id, self.standard)

    def test_several_templates_open_the_wizard_with_the_default_preselected(self):
        second = self._second_template()

        action = self.applicant.action_send_onboarding_link()

        self.assertEqual(action["res_model"], "ninthsense.onboarding.send.wizard")
        self.assertEqual(action["target"], "new")
        self.assertFalse(self._requests())
        wizard = Form(self.env[action["res_model"]].with_context(**action["context"]))
        self.assertEqual(wizard.template_id, self.standard)
        wizard.template_id = second
        result = wizard.save().action_send()

        request = self._requests()
        self._assert_link_dialog(result, request)
        self.assertEqual(request.template_id, second)
        self.assertEqual(request.line_ids.mapped("code"), ["passport", "pan_card"])

    def test_a_resend_preselects_the_request_template(self):
        second = self._second_template()
        configure_portal(self.env)
        invitations.send(self.applicant, ns_config.load(self.env), second, fields.Datetime.now())

        action = self.applicant.action_send_onboarding_link()

        wizard = Form(self.env[action["res_model"]].with_context(**action["context"]))
        self.assertEqual(wizard.template_id, second)

    def test_no_enabled_template_is_refused(self):
        self.standard.sudo().active = False

        with self.assertRaisesRegex(UserError, "Create an onboarding template first."):
            self.applicant.action_send_onboarding_link()
        self.assertFalse(self._requests())

    def test_a_disabled_template_is_refused(self):
        second = self._second_template()
        second.sudo().active = False

        with self.assertRaisesRegex(UserError, "is disabled"):
            invitations.send(
                self.applicant, ns_config.load(self.env), second, fields.Datetime.now()
            )
        self.assertFalse(self._requests())

    def test_the_send_dialog_refuses_a_disabled_template(self):
        second = self._second_template()
        second.sudo().active = False
        wizard = self.env["ninthsense.onboarding.send.wizard"].create(
            {"applicant_id": self.applicant.id, "template_id": second.id}
        )

        with self.assertRaisesRegex(
            UserError, "The onboarding template Foreign National is disabled, so it cannot be sent."
        ):
            wizard.action_send()
        self.assertFalse(self._requests())

    def test_a_resend_with_another_template_records_it_and_asks_for_its_documents(self):
        config = ns_config.load(self.env)
        request, url = invitations.send(
            self.applicant, config, self.standard, fields.Datetime.now()
        )
        self.assertEqual(request.sudo().link_hash, hash_token(url.removeprefix(f"{PORTAL_URL}/s/")))
        old_lines = request.line_ids
        second = self._second_template()

        invitations.send(self.applicant, config, second, fields.Datetime.now())

        self.assertEqual(self._requests(), request)
        self.assertEqual(request.template_id, second)
        self.assertEqual(request.line_ids.mapped("code"), ["passport", "pan_card"])
        self.assertFalse(old_lines.exists())

        invitations.send(self.applicant, config, second, fields.Datetime.now())
        self.assertEqual(request.line_ids.mapped("code"), ["passport", "pan_card"])

    def test_the_dialog_warns_when_no_mail_server_is_configured(self):
        for smtp_server in ("localhost", ""):
            with self.subTest(smtp_server=smtp_server):
                self._no_mail_server(smtp_server)
                action = self.applicant.action_send_onboarding_link()

                self.assertTrue(action["context"]["default_mail_server_missing"])
                dialog = self._assert_link_dialog(action, self._requests())
                self.assertTrue(dialog.mail_server_missing)

    def test_the_dialog_does_not_warn_with_a_mail_server(self):
        self._no_mail_server()
        self.env["ir.mail_server"].sudo().create(
            {"name": "Outgoing", "smtp_host": "smtp.example.test"}
        )

        action = self.applicant.action_send_onboarding_link()

        self.assertFalse(action["context"]["default_mail_server_missing"])
        self.assertFalse(self._assert_link_dialog(action, self._requests()).mail_server_missing)

    def test_a_mail_server_in_odoo_config_counts(self):
        self._no_mail_server("smtp.example.test")
        self.assertFalse(invitations.mail_server_missing(self.env))
        self._no_mail_server(" localhost ")
        self.assertTrue(invitations.mail_server_missing(self.env))

    def test_the_link_dialog_only_closes_and_shows_the_warning(self):
        arch = self.env[LINK_DIALOG].get_views([(False, "form")])["views"]["form"]["arch"]
        self.assertEqual(arch.count("<button"), 1)
        self.assertIn('special="cancel"', arch)
        self.assertIn('widget="CopyClipboardURL"', arch)
        self.assertIn(NO_MAIL_SERVER_WARNING, arch)
        self.assertIn('invisible="not mail_server_missing"', arch)

    def test_send_returns_the_plain_link_without_storing_it(self):
        request, url = invitations.send(
            self.applicant, ns_config.load(self.env), self.standard, fields.Datetime.now()
        )
        token = url.removeprefix(f"{PORTAL_URL}/s/")
        self.assertEqual(request.sudo().link_hash, hash_token(token))
        stored = request.sudo().read()[0]
        self.assertFalse([name for name, value in stored.items() if token in str(value)])
