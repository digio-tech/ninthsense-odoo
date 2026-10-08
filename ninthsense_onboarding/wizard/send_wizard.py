from odoo import fields, models


class OnboardingSendWizard(models.TransientModel):
    _name = "ninthsense.onboarding.send.wizard"
    _description = "Send Onboarding Link"

    applicant_id = fields.Many2one("hr.applicant", required=True, ondelete="cascade")
    template_id = fields.Many2one(
        "ninthsense.onboarding.template",
        string="Template",
        required=True,
        ondelete="cascade",
        domain="[('active', '=', True)]",
    )

    def action_send(self):
        self.ensure_one()
        return self.applicant_id._ninthsense_send_onboarding_link(self.template_id)
