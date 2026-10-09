from odoo import fields, models

from ..core.limits import DEFAULT_LIMITS


class OnboardingDocument(models.Model):
    _name = "ninthsense.onboarding.document"
    _description = "Onboarding Document Received"
    _order = "id"

    request_id = fields.Many2one(
        "ninthsense.onboarding.request", required=True, ondelete="cascade", index=True
    )
    code = fields.Char(required=True)
    verification_document_id = fields.Char(
        size=DEFAULT_LIMITS.verification_document_id_max_length, required=True
    )
    attachment_id = fields.Many2one("ir.attachment", required=True, ondelete="restrict")
    received_at = fields.Datetime()

    _request_verification_unique = models.Constraint(
        "UNIQUE(request_id, verification_document_id)",
        "A received document can be recorded only once per request.",
    )

    def unlink(self):
        attachments = self.attachment_id
        result = super().unlink()
        attachments.sudo().unlink()
        return result
