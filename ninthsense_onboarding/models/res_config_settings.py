from odoo import api, fields, models
from odoo.exceptions import ValidationError

from ..core.config import (
    DEFAULT_LINK_VALIDITY_DAYS,
    MAX_LINK_VALIDITY_DAYS,
    MIN_LINK_VALIDITY_DAYS,
    MIN_SECRET_LENGTH,
)
from ..core.errors import NotConfigured
from ..services import config as settings


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    ninthsense_onboarding_portal_url = fields.Char(
        string="Wrapper Address", config_parameter=settings.PORTAL_URL_KEY
    )
    ninthsense_onboarding_link_validity_days = fields.Integer(
        string="Link Validity (days)",
        config_parameter=settings.LINK_VALIDITY_DAYS_KEY,
        default=DEFAULT_LINK_VALIDITY_DAYS,
    )
    # The secret is write-only: it is never loaded back into this field, and
    # it is cleared from the settings record as soon as it has been stored.
    ninthsense_onboarding_new_secret = fields.Char(string="New Secret")
    ninthsense_onboarding_secret_set = fields.Boolean(
        string="Secret Is Set", compute="_compute_ninthsense_onboarding_secret_set"
    )

    @api.depends_context("uid")
    def _compute_ninthsense_onboarding_secret_set(self):
        stored = self.env["ir.config_parameter"].sudo().get_str(settings.SECRET_KEY, "")
        for record in self:
            record.ninthsense_onboarding_secret_set = bool(stored)

    def _ninthsense_check_values(self, new_secret):
        """Refuse a value the portal link or signature check could not use."""
        url = (self.ninthsense_onboarding_portal_url or "").strip()
        try:
            parsed = settings.parse(
                url or None,
                new_secret or None,
                self.ninthsense_onboarding_link_validity_days,
            )
        except NotConfigured as error:
            raise ValidationError(
                self.env._(
                    "The link validity must be a whole number of days from %(low)s to %(high)s.",
                    low=MIN_LINK_VALIDITY_DAYS,
                    high=MAX_LINK_VALIDITY_DAYS,
                )
            ) from error
        if url and not parsed.portal_url:
            raise ValidationError(
                self.env._(
                    "The wrapper address must be an https address with no path, "
                    "for example https://onboarding.example.com."
                )
            )
        if new_secret and not parsed.secret:
            raise ValidationError(
                self.env._(
                    "The secret must be at least %(length)s characters long.",
                    length=MIN_SECRET_LENGTH,
                )
            )

    def set_values(self):
        new_secret = (self.ninthsense_onboarding_new_secret or "").strip()
        self._ninthsense_check_values(new_secret)
        super().set_values()
        if new_secret:
            self.env["ir.config_parameter"].sudo().set_str(settings.SECRET_KEY, new_secret)
        self.sudo().ninthsense_onboarding_new_secret = False
