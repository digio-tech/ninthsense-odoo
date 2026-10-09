from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError

from ..core.links import portal_state

OPEN_STATES = ("link_sent", "data_received")

#: Every field of a request: only the app sets them, never a user.
_SYSTEM_FIELDS = frozenset(
    {
        "ref",
        "applicant_id",
        "applicant_ref",
        "applicant_name",
        "company_id",
        "template_id",
        "state",
        "cancel_reason",
        "candidate_email",
        "link_hash",
        "link_expires_at",
        "invite_mail_id",
        "invite_state",
        "received_at",
        "results_raw",
        "line_ids",
        "document_ids",
        "value_ids",
        "fill_line_ids",
        "fill_filled_ids",
        "fill_different_ids",
        "fill_invalid_ids",
        "fill_created_ids",
        "fill_failed_ids",
        "filled_at",
        "employee_id",
        "completed_at",
    }
)


class OnboardingRequest(models.Model):
    _name = "ninthsense.onboarding.request"
    _description = "Onboarding Request"
    _inherit = ["mail.thread"]
    _order = "id desc"

    ref = fields.Char(
        required=True,
        readonly=True,
        copy=False,
        default=lambda self: self.env["ir.sequence"].next_by_code("ninthsense.request"),
    )
    applicant_id = fields.Many2one("hr.applicant", ondelete="set null", index=True, readonly=True)
    applicant_ref = fields.Integer(readonly=True)
    applicant_name = fields.Char(readonly=True)
    company_id = fields.Many2one("res.company", required=True, readonly=True)
    template_id = fields.Many2one(
        "ninthsense.onboarding.template", string="Template", readonly=True, ondelete="set null"
    )
    state = fields.Selection(
        [
            ("link_sent", "Link sent"),
            ("data_received", "Data received"),
            ("completed", "Completed"),
            ("cancelled", "Cancelled"),
        ],
        default="link_sent",
        readonly=True,
        tracking=True,
    )
    cancel_reason = fields.Selection(
        [("archived", "Archived"), ("refused", "Refused"), ("deleted", "Deleted")],
        readonly=True,
    )
    candidate_email = fields.Char(readonly=True)
    link_hash = fields.Char(index=True, readonly=True, groups="base.group_system")
    link_expires_at = fields.Datetime(readonly=True)
    link_expired = fields.Boolean(compute="_compute_link_expired")
    invite_mail_id = fields.Many2one("mail.mail", ondelete="set null", index=True, readonly=True)
    invite_state = fields.Selection(
        [("queued", "Queued"), ("sent", "Sent"), ("failed", "Failed")], readonly=True
    )
    invite_failure = fields.Char(string="Email Failure", compute="_compute_invite_failure")
    received_at = fields.Datetime(readonly=True)
    results_raw = fields.Text(readonly=True)
    line_ids = fields.One2many("ninthsense.onboarding.request.line", "request_id", readonly=True)
    document_ids = fields.One2many("ninthsense.onboarding.document", "request_id", readonly=True)
    value_ids = fields.One2many("ninthsense.onboarding.value", "request_id", readonly=True)
    fill_line_ids = fields.One2many("ninthsense.onboarding.fill.line", "request_id", readonly=True)
    # The fill report shows one list per outcome, because a list inside a
    # form cannot be grouped.
    fill_filled_ids = fields.One2many(
        "ninthsense.onboarding.fill.line",
        "request_id",
        domain=[("outcome", "=", "filled")],
        readonly=True,
    )
    fill_different_ids = fields.One2many(
        "ninthsense.onboarding.fill.line",
        "request_id",
        domain=[("outcome", "=", "skipped_different")],
        readonly=True,
    )
    fill_invalid_ids = fields.One2many(
        "ninthsense.onboarding.fill.line",
        "request_id",
        domain=[("outcome", "=", "skipped_invalid")],
        readonly=True,
    )
    fill_created_ids = fields.One2many(
        "ninthsense.onboarding.fill.line",
        "request_id",
        domain=[("outcome", "=", "created")],
        readonly=True,
    )
    fill_failed_ids = fields.One2many(
        "ninthsense.onboarding.fill.line",
        "request_id",
        domain=[("outcome", "=", "attach_failed")],
        readonly=True,
    )
    filled_at = fields.Datetime(readonly=True)
    employee_id = fields.Many2one("hr.employee", ondelete="set null", readonly=True)
    completed_at = fields.Datetime(readonly=True)

    _ref_unique = models.Constraint("UNIQUE(ref)", "A request reference must be unique.")

    def write(self, vals):
        """Refuse a user's change to anything the app manages.

        Officers may write to a request only so they can post on its chatter.
        Every change the app makes runs as superuser.
        """
        if not self.env.su and not _SYSTEM_FIELDS.isdisjoint(vals):
            raise AccessError(self.env._("Onboarding requests are only changed by the app."))
        return super().write(vals)

    @api.depends("invite_state", "invite_mail_id.failure_reason")
    def _compute_invite_failure(self):
        """The mail system's reason the invitation failed, read as superuser.

        Officers cannot read the mail queue, but they need the reason to act on it.
        """
        for request in self:
            failure = False
            if request.invite_state == "failed":
                failure = request.sudo().invite_mail_id.failure_reason or self.env._(
                    "no reason was given"
                )
            request.invite_failure = failure

    @api.depends("state", "link_expires_at")
    def _compute_link_expired(self):
        now = fields.Datetime.now()
        for request in self:
            request.link_expired = bool(
                request.state == "link_sent"
                and request.link_expires_at
                and request.link_expires_at < now
            )

    @api.constrains("applicant_id", "state")
    def _check_one_open_request(self):
        for request in self:
            if not request.applicant_id or request.state not in OPEN_STATES:
                continue
            others = self.search_count(
                [
                    ("applicant_id", "=", request.applicant_id.id),
                    ("state", "in", OPEN_STATES),
                    ("id", "!=", request.id),
                ]
            )
            if others:
                raise ValidationError(
                    self.env._("This applicant already has an open onboarding request.")
                )

    def unlink(self):
        self.document_ids.unlink()
        return super().unlink()

    def _ninthsense_portal_state(self, now):
        """The state the candidate portal sees for this request's link."""
        self.ensure_one()
        return portal_state(self.state, self.link_expires_at, now)

    def _ninthsense_cancel(self, reason):
        """Cancel the request and revoke its link."""
        self.sudo().write({"state": "cancelled", "cancel_reason": reason, "link_hash": False})

    def _ninthsense_snapshot_lines(self, template):
        """Record the template and copy its lines into this request, replacing any it has."""
        self.ensure_one()
        commands = [(5, 0, 0)]
        commands.extend(
            (
                0,
                0,
                {
                    "sequence": line.sequence,
                    "code": line.document_type_id.code,
                    "label": line.document_type_id.name,
                    "mandatory": line.mandatory,
                    "accept": line.accept,
                    "max_mb": line.max_mb,
                },
            )
            for line in template.line_ids
        )
        self.sudo().write({"template_id": template.id, "line_ids": commands})
