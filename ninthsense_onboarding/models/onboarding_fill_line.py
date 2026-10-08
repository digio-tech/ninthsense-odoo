from odoo import fields, models


class OnboardingFillLine(models.Model):
    _name = "ninthsense.onboarding.fill.line"
    _description = "Onboarding Fill Report Line"
    _order = "sequence, id"

    request_id = fields.Many2one(
        "ninthsense.onboarding.request", required=True, ondelete="cascade", index=True
    )
    sequence = fields.Integer()
    outcome = fields.Selection(
        [
            ("filled", "Filled"),
            ("skipped_different", "Skipped — already filled"),
            ("skipped_invalid", "Skipped — invalid"),
            ("created", "Created on save"),
            ("attach_failed", "Attachments that failed"),
        ]
    )
    label = fields.Char()
    value = fields.Char()
    current_value = fields.Char()
    reason = fields.Char()
