from odoo import api, fields, models


class OnboardingLinkDialog(models.TransientModel):
    """Shows HR the link just sent, so they can pass it on another way.

    The dialog is never saved: its values arrive as defaults in the action's
    context and its only button discards it, so the plain link is not stored.
    """

    _name = "ninthsense.onboarding.link.dialog"
    _description = "Onboarding Link"

    email = fields.Char(readonly=True)
    url = fields.Char(string="Link", readonly=True)
    mail_server_missing = fields.Boolean(readonly=True)
    message = fields.Char(compute="_compute_message")

    @api.depends("email")
    def _compute_message(self):
        for dialog in self:
            dialog.message = self.env._("Onboarding link sent to %(email)s", email=dialog.email)

    @api.model
    def _action_open(self, email, url, mail_server_missing):
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Onboarding link"),
            "res_model": self._name,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
            "context": {
                "default_email": email,
                "default_url": url,
                "default_mail_server_missing": mail_server_missing,
            },
        }
