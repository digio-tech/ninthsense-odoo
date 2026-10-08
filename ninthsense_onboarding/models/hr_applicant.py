from odoo import api, fields, models

from ..core import log
from ..core.errors import NotConfigured
from ..services import config as settings
from ..services import employee_fill, invitations
from .onboarding_request import OPEN_STATES

_RECRUITMENT_USER = "hr_recruitment.group_hr_recruitment_user"


class HrApplicant(models.Model):
    _inherit = "hr.applicant"

    onboarding_request_ids = fields.One2many(
        "ninthsense.onboarding.request",
        "applicant_id",
        string="Onboarding Requests",
        groups=_RECRUITMENT_USER,
    )
    onboarding_request_id = fields.Many2one(
        "ninthsense.onboarding.request",
        string="Open Onboarding Request",
        compute="_compute_onboarding_request_id",
        groups=_RECRUITMENT_USER,
    )

    onboarding_request_count = fields.Integer(
        compute="_compute_onboarding_request_count",
        groups=_RECRUITMENT_USER,
    )
    onboarding_latest_state = fields.Selection(
        selection=lambda self: self.env["ninthsense.onboarding.request"]._fields["state"].selection,
        string="Onboarding Status",
        compute="_compute_onboarding_latest_state",
        groups=_RECRUITMENT_USER,
    )

    @api.depends("onboarding_request_ids")
    def _compute_onboarding_request_count(self):
        for applicant in self:
            applicant.onboarding_request_count = len(applicant.onboarding_request_ids)

    @api.depends("onboarding_request_ids.state")
    def _compute_onboarding_latest_state(self):
        """The state of the open request if there is one, else of the most recent."""
        for applicant in self:
            requests = applicant.onboarding_request_ids
            open_requests = requests.filtered(lambda request: request.state in OPEN_STATES)
            latest = (open_requests or requests).sorted("id", reverse=True)[:1]
            applicant.onboarding_latest_state = latest.state

    def action_open_onboarding_requests(self):
        """Open the applicant's only request, or the list of its requests."""
        self.ensure_one()
        action = {
            "type": "ir.actions.act_window",
            "res_model": "ninthsense.onboarding.request",
            "target": "current",
        }
        if len(self.onboarding_request_ids) == 1:
            return dict(
                action,
                name=self.env._("Onboarding Request"),
                view_mode="form",
                views=[(False, "form")],
                res_id=self.onboarding_request_ids.id,
            )
        return dict(
            action,
            name=self.env._("Onboarding Requests"),
            view_mode="list,form",
            views=[(False, "list"), (False, "form")],
            domain=[("applicant_id", "=", self.id)],
        )

    @api.depends("onboarding_request_ids.state")
    def _compute_onboarding_request_id(self):
        for applicant in self:
            applicant.onboarding_request_id = applicant.onboarding_request_ids.filtered(
                lambda request: request.state in OPEN_STATES
            )[:1]

    def write(self, vals):
        result = super().write(vals)
        if vals.get("active") is False:
            for applicant in self:
                reason = "refused" if applicant.refuse_reason_id else "archived"
                applicant._ninthsense_cancel_open_requests(reason)
        return result

    def unlink(self):
        self._ninthsense_cancel_open_requests("deleted")
        return super().unlink()

    def _ninthsense_cancel_open_requests(self, reason):
        """Cancel the open requests of these applicants and revoke their links.

        Runs as superuser because the user archiving, refusing or deleting an
        applicant may not be allowed to edit its requests, and a link must not
        outlive the applicant it was issued for.
        """
        requests = self.sudo().onboarding_request_ids.filtered(
            lambda request: request.state in OPEN_STATES
        )
        for request in requests:
            request._ninthsense_cancel(reason)
            log.event("request_cancelled", outcome=reason, request_id=request.id)

    def action_send_onboarding_link(self):
        """Send with the only enabled template, or let HR pick one when there are several."""
        self.ensure_one()
        invitations.check_applicant(self)
        templates = self.env["ninthsense.onboarding.template"].search([])
        if not templates:
            raise invitations.no_template_error(self.env)
        if len(templates) == 1:
            return self._ninthsense_send_onboarding_link(templates)
        current = self.onboarding_request_id.template_id
        preselected = current if current in templates else templates.filtered("is_default")[:1]
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Send onboarding link"),
            "res_model": "ninthsense.onboarding.send.wizard",
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
            "context": {
                "default_applicant_id": self.id,
                "default_template_id": preselected.id,
            },
        }

    def _ninthsense_send_onboarding_link(self, template):
        """Email the candidate a fresh onboarding link for `template` and show HR the link.

        The form reloads when the dialog closes.
        """
        self.ensure_one()
        try:
            config = settings.load(self.env)
        except NotConfigured as error:
            raise invitations.not_configured_error(self.env) from error
        request, url = invitations.send(self, config, template, fields.Datetime.now())
        return self.env["ninthsense.onboarding.link.dialog"]._action_open(
            request.candidate_email, url, invitations.mail_server_missing(self.env)
        )

    def create_employee_from_applicant(self):
        """Odoo's Create Employee, which also completes an open request holding data.

        Once an employee is linked, Odoo hides the button, and a direct call
        opens that employee rather than letting Odoo create a second one.
        Otherwise Odoo creates and saves the employee, with the request's fill
        applied to its values, and the request is completed in the same
        transaction. Without data, Odoo's own behaviour applies and the
        request is left as it is.
        """
        self.ensure_one()
        if self.employee_id:
            return self.action_open_employee()
        request = self._ninthsense_fill_request()
        action = super().create_employee_from_applicant()
        if request:
            self.employee_id._ninthsense_complete_request(request)
        return action

    def _get_employee_create_vals(self):
        """Odoo's values, with each empty mapped field filled from the open request's data."""
        vals = super()._get_employee_create_vals()
        request = self._ninthsense_fill_request()
        if not request:
            return vals
        return employee_fill.filled_values(self, request, vals)

    def _ninthsense_fill_request(self):
        """The open request, as superuser, if it holds data to fill the employee with."""
        self.ensure_one()
        return self.sudo().onboarding_request_id.filtered("value_ids")
