from odoo import api, fields, models


class OnboardingValue(models.Model):
    _name = "ninthsense.onboarding.value"
    _description = "Onboarding Parsed Value"
    _order = "id"

    request_id = fields.Many2one(
        "ninthsense.onboarding.request", required=True, ondelete="cascade", index=True
    )
    field_key = fields.Char(required=True)
    label = fields.Char()
    value = fields.Char()
    source_code = fields.Char()
    source_name = fields.Char(string="Document", compute="_compute_source_name")

    @api.depends("source_code")
    def _compute_source_name(self):
        names = {
            doc_type.code: doc_type.name
            for doc_type in self.env["ninthsense.onboarding.document.type"].search([])
        }
        for value in self:
            value.source_name = names.get(value.source_code) or value.source_code
