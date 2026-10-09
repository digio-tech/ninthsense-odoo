"""Sending the onboarding link: one request per applicant, one queued email per send."""

from odoo.exceptions import UserError
from odoo.tools import config as odoo_config

from ..core import links, log
from ..core.errors import NotConfigured
from ..models.onboarding_request import OPEN_STATES

_TEMPLATE_XMLID = "ninthsense.mail_template_onboarding_link"
_MAIL_CRON_XMLID = "mail.ir_cron_mail_scheduler_action"
_DEFAULT_SMTP_SERVER = "localhost"

#: What a request's `invite_state` becomes for each state its `mail.mail` passes through.
INVITE_STATE_BY_MAIL_STATE = {
    "outgoing": "queued",
    "sent": "sent",
    "received": "sent",
    "exception": "failed",
    "cancel": "failed",
}


def not_configured_error(env):
    return UserError(
        env._(
            "9thSense is not set up yet. An administrator must enter the wrapper "
            "address and secret in Settings."
        )
    )


def no_template_error(env):
    return UserError(env._("Create an onboarding template first."))


def mail_server_missing(env):
    """Whether Odoo has nowhere to send email: no outgoing mail server and no SMTP host set."""
    smtp_server = str(odoo_config.get("smtp_server") or "").strip()
    return not (
        env["ir.mail_server"].sudo().search_count([], limit=1)
        or (smtp_server and smtp_server != _DEFAULT_SMTP_SERVER)
    )


def check_applicant(applicant):
    """Refuse an applicant who is archived, already an employee, or not hired yet."""
    env = applicant.env
    if not applicant.active:
        raise UserError(env._("The applicant is archived, so no onboarding link can be sent."))
    if applicant.employee_id:
        raise UserError(
            env._("The applicant already has an employee, so no onboarding link can be sent.")
        )
    if not applicant.date_closed:
        raise UserError(env._("The applicant is not hired yet, so no onboarding link can be sent."))


def send(applicant, config, template, now):
    """Issue a fresh link for `applicant` with `template`, queue its email.

    Returns `(request, url)`. The applicant's open request is reused, so a
    resend never creates a second one and keeps whatever the candidate
    already sent. A resend with another template records it and asks for its
    documents instead. Only the token's hash is stored; the plain URL lives in
    the queued email and in the return value, for HR to see once. Any earlier
    link stops working. Everything happens in the caller's transaction, so a
    failure leaves no request, hash or status behind.
    """
    applicant.ensure_one()
    env = applicant.env
    check_applicant(applicant)
    if not template:
        raise no_template_error(env)
    if not template.active:
        raise UserError(
            env._(
                "The onboarding template %(template)s is disabled, so it cannot be sent.",
                template=template.display_name,
            )
        )
    if not applicant.email_from:
        raise UserError(
            env._("The applicant has no email address, so no onboarding link can be sent.")
        )
    try:
        config.require_ready()
    except NotConfigured as error:
        raise not_configured_error(env) from error

    Request = env["ninthsense.onboarding.request"].sudo()
    request = Request.search(
        [("applicant_id", "=", applicant.id), ("state", "in", OPEN_STATES)], limit=1
    )
    if not request:
        request = Request.create(
            {
                "company_id": applicant.company_id.id or env.company.id,
                "applicant_id": applicant.id,
                "applicant_ref": applicant.id,
                "applicant_name": applicant.partner_name or applicant.display_name,
            }
        )
    if request.template_id != template:
        request._ninthsense_snapshot_lines(template)

    token = links.mint_token()
    url = f"{config.portal_url}/s/{token}"
    request.write(
        {
            "link_hash": links.hash_token(token),
            "link_expires_at": links.expiry(now, config.link_validity_days),
            "state": "link_sent",
            "candidate_email": applicant.email_from,
        }
    )

    try:
        mail_id = (
            env.ref(_TEMPLATE_XMLID)
            .with_context(
                portal_url=url,
                link_validity_days=config.link_validity_days,
            )
            .send_mail(request.id, force_send=False)
        )
    except Exception as error:
        raise UserError(
            env._("The onboarding email could not be prepared. Nothing was sent.")
        ) from error
    mail = env["mail.mail"].sudo().browse(mail_id)
    request.write(
        {
            "invite_mail_id": mail_id,
            "invite_state": INVITE_STATE_BY_MAIL_STATE.get(mail.state, False),
        }
    )
    env.ref(_MAIL_CRON_XMLID).sudo()._trigger()

    log.event("link_issued", outcome="queued", request_id=request.id)
    return request.with_env(env), url
