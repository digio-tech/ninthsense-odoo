"""Fill a new employee's values from a request, and record its fill report."""

from odoo import fields
from odoo.tools.misc import clean_context

from ..core import fill, log, mapping_rules


def reason_text(env, reason):
    """The translated text shown in the fill report for a reason code."""
    texts = {
        fill.NEVER_FILLED: env._("Yes/no fields are never filled from 9thSense data."),
        fill.UNKNOWN_FIELD: env._("The employee has no such field."),
        fill.UNSUPPORTED_TYPE: env._("This kind of field cannot be filled."),
        fill.INVALID_DATE: env._("Not a valid date."),
        fill.NOT_IN_PAST: env._("The date is not in the past."),
        fill.TOO_LONG: env._("Too long for the field."),
        fill.INVALID_EMAIL: env._("Not a valid email address."),
        fill.NOT_A_CHOICE: env._("Not one of the field's choices."),
        fill.NO_MATCH: env._("No matching record."),
        fill.SEVERAL_MATCHES: env._("More than one matching record."),
        fill.NO_COUNTRY: env._("No country to find the state in."),
        fill.AADHAAR_UNREADABLE: env._("The Aadhaar number could not be read."),
        fill.NO_ACCOUNT_NUMBER: env._("No bank account number was read."),
        fill.INVALID_IFSC: env._("Not a valid IFSC code."),
        fill.INCOMPLETE_EDUCATION: env._("Education needs a degree or an institution."),
        fill.INCOMPLETE_EXPERIENCE: env._("Previous employment needs an employer."),
    }
    return texts.get(reason, reason)


def report_line_values(env, request, rows):
    """`ninthsense.onboarding.fill.line` values for report rows, in order."""
    return [
        {
            "request_id": request.id,
            "sequence": index,
            "outcome": row.outcome,
            "label": row.label,
            "value": row.value,
            "current_value": row.current_value,
            "reason": reason_text(env, row.reason) if row.reason else False,
        }
        for index, row in enumerate(rows)
    ]


def mapping_rows(request):
    """The `(key, source_code, fallback_code)` rows of the request's template, as they stand now.

    A request with no template has no rows, so nothing is filled.
    """
    return [
        (row.field_key, row.source_type_id.code, row.fallback_type_id.code or None)
        for row in request.sudo().template_id.mapping_ids
    ]


def chosen_values(request):
    """Catalogue key -> the stored value its mapping row chooses, for every mapped key."""
    values = {
        (value.field_key, value.source_code): value.value
        for value in request.value_ids
        if value.value
    }
    return mapping_rules.choose(values, mapping_rows(request))


def _start(employees, vals, targets):
    """The values the mapped fields hold before the fill: Odoo's defaults, then `vals`."""
    start = employees.default_get(list(targets))
    start.update({name: vals[name] for name in targets if name in vals})
    for name in targets:
        field = employees._fields[name]
        if field.type == "many2one" and start.get(name):
            record = employees.env[field.comodel_name].browse(start[name])
            start[name] = (record.id, record.display_name)
    if not start.get("legal_name"):
        # Legal name is a stored compute that follows the name when left empty.
        start["legal_name"] = vals.get("name")
    return start


def _matches(env, values, start):
    country_name, state_name = fill.address_names(values)
    countries = {}
    states = {}
    country_ids = []
    if country_name:
        country_ids = env["res.country"].search([("name", "=ilike", country_name)]).ids
        countries[country_name] = country_ids
    if state_name:
        candidates = set(country_ids)
        current = start.get(fill.COUNTRY)
        if current:
            candidates.add(current[0])
        found = env["res.country.state"].search(
            [("country_id", "in", list(candidates)), ("name", "=ilike", state_name)]
        )
        for country_id in candidates:
            states[(country_id, state_name)] = found.filtered(
                lambda state, country_id=country_id: state.country_id.id == country_id
            ).ids
    return {"country": countries, "state": states}


def filled_values(applicant, request, vals):
    """`vals` with every empty mapped field filled from the request, after replacing its report.

    `vals` are the values Odoo creates the applicant's employee with. A mapped
    field counts as empty when neither they nor the employee's defaults give
    it a value.
    """
    env = applicant.env
    employees = env["hr.employee"].with_context(clean_context(env.context))
    targets = [name for name in fill.employee_targets() if name in employees._fields]
    start = _start(employees, vals, targets)
    fields_info = employees.fields_get(targets, ["type", "size", "selection"])
    values = chosen_values(request)
    result = fill.build(start, values, fields_info, _matches(env, values, start))

    request = request.sudo()
    request.fill_line_ids.unlink()
    env["ninthsense.onboarding.fill.line"].sudo().create(
        report_line_values(env, request, result.report)
    )
    request.write({"filled_at": fields.Datetime.now()})
    log.event(
        "employee_filled",
        outcome="ok",
        request_id=request.id,
        applicant_id=applicant.id,
        count=len(result.fill),
    )
    return dict(vals, **result.fill)
