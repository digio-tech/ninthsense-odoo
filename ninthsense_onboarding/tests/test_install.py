from odoo.addons.base.tests.common import BaseCommon
from odoo.modules.module import get_manifest
from odoo.tools.misc import file_path

MODULE = "ninthsense_onboarding"


class TestInstall(BaseCommon):
    def test_module_is_installed(self):
        module = self.env["ir.module.module"].search([("name", "=", MODULE)])
        self.assertEqual(module.state, "installed")

    def test_manifest_version(self):
        self.assertEqual(get_manifest(MODULE)["version"], "20.0.1.0.0")

    def test_store_listing_metadata(self):
        manifest = get_manifest(MODULE)
        self.assertEqual(manifest["license"], "LGPL-3")
        self.assertFalse(manifest["application"])
        self.assertTrue(manifest["summary"])
        self.assertTrue(manifest["description"].strip())
        self.assertTrue(file_path(f"{MODULE}/static/description/icon.png"))

    def test_seed_data_is_present(self):
        template = self.env.ref(f"{MODULE}.template_onboarding").sudo()
        self.assertEqual(template.name, "Standard Onboarding")
        self.assertTrue(template.is_default)
        self.assertTrue(template.active)
        self.assertEqual(len(template.line_ids), 9)
        self.assertEqual(len(template.mapping_ids), 25)
        self.assertEqual(
            self.env["ninthsense.onboarding.document.type"].sudo().search_count([]), 14
        )
        self.assertFalse(self.env.ref(f"{MODULE}.clearing_label_in", raise_if_not_found=False))
        self.assertTrue(self.env.ref(f"{MODULE}.mail_template_onboarding_link"))
