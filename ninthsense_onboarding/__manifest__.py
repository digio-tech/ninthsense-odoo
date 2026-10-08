{
    "name": "9thSense Onboarding",
    "version": "20.0.1.0.0",
    "category": "Human Resources/Recruitment",
    "summary": "Collect a hired applicant's documents through 9thSense and fill the new employee",
    "description": """
Send a hired applicant a 9thSense onboarding link from the applicant form. The
candidate uploads their documents, 9thSense reads them, and Create Employee
fills the new employee's empty fields from what was read: personal details,
address, identity numbers, bank account and résumé lines.

- Onboarding templates choose the documents to collect and which document fills each field.
- Values from HR or Odoo are never overwritten, and a report shows what was filled and skipped.
- Aadhaar numbers are stored masked.

Requires a 9thSense account and its onboarding portal.
""",
    "author": "Digio Labs",
    "license": "LGPL-3",
    "application": False,
    "depends": ["hr", "hr_recruitment", "hr_skills"],
    "external_dependencies": {"python": ["jsonschema"]},
    "post_load": "post_load",
    "uninstall_hook": "uninstall_hook",
    "data": [
        "security/ir.access.csv",
        "security/security_rules.xml",
        "data/ir_sequence_data.xml",
        "data/document_type_data.xml",
        "data/template_data.xml",
        "data/mail_template_data.xml",
        "views/onboarding_request_views.xml",
        "views/hr_applicant_views.xml",
        "views/res_config_settings_views.xml",
        "views/onboarding_template_views.xml",
        "wizard/send_wizard_views.xml",
        "wizard/link_dialog_views.xml",
    ],
    "assets": {
        "web.assets_tests": ["ninthsense_onboarding/static/tests/tours/*.js"],
    },
}
