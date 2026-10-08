from odoo import models

from ..services.invitations import INVITE_STATE_BY_MAIL_STATE


class MailMail(models.Model):
    _inherit = "mail.mail"

    def write(self, vals):
        """Copy an onboarding email's delivery state onto its request.

        The request keeps its own copy so HR can see whether the candidate's
        email went out without opening the mail queue.
        """
        result = super().write(vals)
        invite_state = INVITE_STATE_BY_MAIL_STATE.get(vals.get("state"))
        if invite_state and self.ids:
            requests = (
                self.env["ninthsense.onboarding.request"]
                .sudo()
                .search([("invite_mail_id", "in", self.ids)])
            )
            if requests:
                requests.write({"invite_state": invite_state})
        return result
