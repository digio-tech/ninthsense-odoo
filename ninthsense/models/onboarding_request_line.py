from odoo import api, fields, models
from odoo.exceptions import ValidationError

from ..core.limits import DEFAULT_LIMITS


class OnboardingRequestLine(models.Model):
    _name = "ninthsense.onboarding.request.line"
    _description = "Onboarding Request Document Line"
    _order = "sequence, id"

    request_id = fields.Many2one(
        "ninthsense.onboarding.request", required=True, ondelete="cascade", index=True
    )
    sequence = fields.Integer()
    code = fields.Char(required=True)
    label = fields.Char(required=True)
    mandatory = fields.Boolean()
    accept = fields.Char()
    max_mb = fields.Integer()

    _request_code_unique = models.Constraint(
        "UNIQUE(request_id, code)", "A document can be asked for only once per request."
    )

    @api.constrains("max_mb")
    def _check_max_mb(self):
        cap = DEFAULT_LIMITS.file_max_mb
        for line in self:
            if line.max_mb > cap:
                raise ValidationError(self.env._("The maximum file size cannot exceed %s MB.", cap))
