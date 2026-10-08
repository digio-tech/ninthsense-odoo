from odoo import fields, models


class OnboardingDocumentType(models.Model):
    _name = "ninthsense.onboarding.document.type"
    _description = "Onboarding Document Type"
    _order = "sequence, id"

    code = fields.Char(required=True)
    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer()

    _code_unique = models.Constraint("UNIQUE(code)", "A document type code must be unique.")
