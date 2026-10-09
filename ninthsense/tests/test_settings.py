from odoo.addons.base.tests.common import BaseCommon
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import new_test_user

from ..core.links import hash_token
from .test_send import PORTAL_URL, hired_applicant

URL_KEY = "ninthsense.portal_url"
SECRET_KEY = "ninthsense.secret"
DAYS_KEY = "ninthsense.link_validity_days"
SECRET = "k" * 40
NEW_SECRET = "n" * 40


class TestOnboardingSettings(BaseCommon):
    _test_user_groups = (
        "base.group_user",
        "base.group_system",
        "hr_recruitment.group_hr_recruitment_manager",
    )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(user=cls._test_user)
        cls.params = cls.env["ir.config_parameter"].sudo()
        cls.Settings = cls.env["res.config.settings"]

    def _save(self, **values):
        settings = self.Settings.create(
            {
                "ninthsense_onboarding_portal_url": PORTAL_URL,
                "ninthsense_onboarding_link_validity_days": 14,
                **{f"ninthsense_onboarding_{key}": value for key, value in values.items()},
            }
        )
        settings.execute()
        return settings

    def test_saving_stores_the_three_parameters(self):
        self._save(
            portal_url="https://portal.example.test", new_secret=SECRET, link_validity_days=30
        )
        self.assertEqual(self.params.get_str(URL_KEY), "https://portal.example.test")
        self.assertEqual(self.params.get_str(SECRET_KEY), SECRET)
        self.assertEqual(self.params.get_str(DAYS_KEY), "30")

    def test_reopening_shows_an_empty_secret_and_that_one_is_set(self):
        self._save(new_secret=SECRET)
        values = self.Settings.default_get(
            ["ninthsense_onboarding_new_secret", "ninthsense_onboarding_secret_set"]
        )
        self.assertFalse(values.get("ninthsense_onboarding_new_secret"))
        reopened = self.Settings.create({})
        self.assertFalse(reopened.ninthsense_onboarding_new_secret)
        self.assertTrue(reopened.ninthsense_onboarding_secret_set)

    def test_secret_is_not_set_before_one_is_saved(self):
        self.params.search([("key", "=", SECRET_KEY)]).unlink()
        self.assertFalse(self.Settings.create({}).ninthsense_onboarding_secret_set)

    def test_an_empty_new_secret_keeps_the_old_one(self):
        self._save(new_secret=SECRET)
        self._save(new_secret="", link_validity_days=20)
        self.assertEqual(self.params.get_str(SECRET_KEY), SECRET)
        self.assertEqual(self.params.get_str(DAYS_KEY), "20")

    def test_a_new_secret_replaces_the_old_one(self):
        self._save(new_secret=SECRET)
        self._save(new_secret=NEW_SECRET)
        self.assertEqual(self.params.get_str(SECRET_KEY), NEW_SECRET)

    def test_the_secret_never_comes_back_through_read(self):
        settings = self._save(new_secret=SECRET)
        for record in (settings, self.Settings.create({})):
            data = record.read()[0]
            self.assertNotIn(SECRET, [str(value) for value in data.values()])
            self.assertFalse(data["ninthsense_onboarding_new_secret"])
            self.assertFalse(record.sudo().ninthsense_onboarding_new_secret)

    def test_bad_values_are_refused_and_nothing_is_stored(self):
        self._save(new_secret=SECRET)
        bad = (
            {"portal_url": "https://portal.example.test/path"},
            {"portal_url": "ftp://portal.example.test"},
            {"new_secret": "s" * 10},
            {"link_validity_days": 0},
            {"link_validity_days": 91},
        )
        for values in bad:
            with self.subTest(values=values), self.assertRaises(ValidationError):
                self._save(**values)
        self.assertEqual(self.params.get_str(URL_KEY), PORTAL_URL)
        self.assertEqual(self.params.get_str(SECRET_KEY), SECRET)

    def test_a_non_admin_cannot_read_the_parameters(self):
        user = new_test_user(
            self.env,
            login="plain_manager",
            groups="base.group_user,hr_recruitment.group_hr_recruitment_manager",
        )
        with self.assertRaises(AccessError):
            self.env["ir.config_parameter"].with_user(user).get_str(SECRET_KEY)

    def test_send_uses_the_configured_url_in_the_link(self):
        self._save(portal_url="https://other.example.test", new_secret=SECRET)
        applicant = hired_applicant(
            self.env, {"partner_name": "Asha Rao", "email_from": "asha.settings@example.test"}
        )
        applicant.action_send_onboarding_link()
        request = applicant.onboarding_request_id
        body = request.invite_mail_id.sudo().body_html
        marker = "https://other.example.test/s/"
        self.assertIn(marker, body)
        start = body.index(marker) + len(marker)
        end = start
        while body[end] not in "\"'<& ":
            end += 1
        self.assertEqual(request.sudo().link_hash, hash_token(body[start:end]))

    def test_uninstall_removes_every_addon_parameter_and_nothing_else(self):
        from .. import uninstall_hook

        self._save(new_secret=SECRET)
        self.params.set_str("ninthsense.anything_else", "x")
        self.params.set_str("ninthsenseXonboarding.other", "kept")

        uninstall_hook(self.env)

        keys = self.params.search([("key", "=like", "ninthsense%")]).mapped("key")
        self.assertEqual([key for key in keys if key.startswith("ninthsense.")], [])
        self.assertIn("ninthsenseXonboarding.other", keys)
