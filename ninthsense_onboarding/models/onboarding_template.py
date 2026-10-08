from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import SQL

from ..core import mapping_rules
from ..core.catalogue import CATALOGUE, ENTRIES
from ..core.limits import DEFAULT_LIMITS

MIN_FILE_MB = 1

_SAVING = "ninthsense_template_saving"


class _Saving:
    """Set in the context while a template saves its documents and mapping together.

    Lines and mapping rows written during the save collect their templates
    here instead of checking them at once, so a line and the rows that read it
    can be removed in the same save. The save then checks them all. A client
    cannot send this object in an RPC context, so it cannot skip the checks.
    """

    __slots__ = ("template_ids",)

    def __init__(self):
        self.template_ids = set()


def _check_now_or_after_save(templates):
    """Check the templates' documents and mapping, or leave it to the save in progress."""
    saving = templates.env.context.get(_SAVING)
    if isinstance(saving, _Saving):
        saving.template_ids.update(templates.ids)
    else:
        templates.exists()._check_lines_and_mapping()


def field_name(entry):
    """How a catalogue field is named to HR: its section, then its label."""
    return f"{entry.section}: {entry.label}"


FIELD_KEY_SELECTION = [(entry.key, field_name(entry)) for entry in ENTRIES]


class OnboardingTemplate(models.Model):
    _name = "ninthsense.onboarding.template"
    _description = "Onboarding Template"
    _order = "is_default desc, name, id"

    name = fields.Char(required=True)
    active = fields.Boolean(string="Enabled", default=True)
    is_default = fields.Boolean(string="Default", copy=False)
    description = fields.Text()
    line_ids = fields.One2many(
        "ninthsense.onboarding.template.line", "template_id", string="Documents", copy=True
    )
    mapping_ids = fields.One2many(
        "ninthsense.onboarding.template.mapping",
        "template_id",
        string="Field Mapping",
        copy=True,
    )
    document_count = fields.Integer(string="Document Count", compute="_compute_document_count")

    _name_unique = models.Constraint(
        "UNIQUE(name)", "An onboarding template with this name already exists."
    )
    _one_default = models.UniqueIndex(
        "(is_default) WHERE is_default", "Only one onboarding template can be the default."
    )

    @api.depends("line_ids")
    def _compute_document_count(self):
        for template in self:
            template.document_count = len(template.line_ids)

    @api.constrains("line_ids", "mapping_ids")
    def _check_lines_and_mapping(self):
        for template in self:
            if not template.line_ids:
                raise ValidationError(
                    self.env._("The template must ask for at least one document.")
                )
            template._ninthsense_check_mapping()

    def _ninthsense_check_mapping(self):
        """Refuse a mapping that breaks the rules, naming the first field at fault."""
        self.ensure_one()
        rows = [
            (row.field_key, row.source_type_id.code or None, row.fallback_type_id.code or None)
            for row in self.mapping_ids
        ]
        problems = mapping_rules.mapping_problems(
            rows, self.line_ids.document_type_id.mapped("code")
        )
        if problems:
            raise ValidationError(self._ninthsense_problem_text(problems[0]))

    def _ninthsense_problem_text(self, problem):
        entry = CATALOGUE.get(problem.key)
        field = field_name(entry) if entry else problem.key
        texts = {
            mapping_rules.UNKNOWN_FIELD: self.env._(
                "%(field)s is not a field 9thSense can fill.", field=field
            ),
            mapping_rules.MAPPED_TWICE: self.env._(
                "%(field)s is mapped more than once.", field=field
            ),
            mapping_rules.SOURCE_NOT_ALLOWED: self.env._(
                "%(field)s: the source document must be one of the template's documents "
                "that can supply this field.",
                field=field,
            ),
            mapping_rules.FALLBACK_NOT_ALLOWED: self.env._(
                "%(field)s: the fallback document must be one of the template's documents "
                "that can supply this field.",
                field=field,
            ),
            mapping_rules.FALLBACK_IS_SOURCE: self.env._(
                "%(field)s: the fallback document must differ from the source.", field=field
            ),
        }
        return texts[problem.kind]

    @api.model_create_multi
    def create(self, vals_list):
        self._ninthsense_lock()
        defaults = [index for index, vals in enumerate(vals_list) if vals.get("is_default")]
        if defaults:
            vals_list = [
                dict(vals, is_default=False) if index in defaults[:-1] else vals
                for index, vals in enumerate(vals_list)
            ]
            self._ninthsense_clear_default()
        saving = _Saving()
        templates = super(OnboardingTemplate, self.with_context(**{_SAVING: saving})).create(
            vals_list
        )
        templates = templates.with_env(self.env)
        (templates | self.browse(saving.template_ids)).exists()._check_lines_and_mapping()
        templates._ninthsense_settle_default(enabled=templates)
        return templates

    def write(self, vals):
        if not {"active", "is_default"} & set(vals):
            return self._ninthsense_write_and_check(vals)
        self._ninthsense_lock()
        if vals.get("active") is False:
            self._ninthsense_check_default_can_go()
            if "is_default" not in vals:
                vals = dict(vals, is_default=False)
        enabled = self.browse()
        if vals.get("active"):
            enabled = self.filtered(lambda template: not template.active)
        if vals.get("is_default"):
            self._ninthsense_clear_default()
        result = self._ninthsense_write_and_check(vals)
        self._ninthsense_settle_default(enabled=enabled)
        return result

    def unlink(self):
        self._ninthsense_lock()
        self._ninthsense_check_default_can_go()
        return super().unlink()

    @api.ondelete(at_uninstall=False)
    def _unlink_except_used(self):
        requests = self.env["ninthsense.onboarding.request"].sudo()
        if requests.search_count([("template_id", "in", self.ids)], limit=1):
            raise UserError(
                self.env._(
                    "This template has been used for onboarding requests. Disable it instead."
                )
            )

    def _ninthsense_write_and_check(self, vals):
        """Write, then check every template whose lines or mapping rows the write changed."""
        saving = _Saving()
        result = super(OnboardingTemplate, self.with_context(**{_SAVING: saving})).write(vals)
        self.browse(saving.template_ids).exists()._check_lines_and_mapping()
        return result

    def _ninthsense_lock(self):
        """Lock every template, so concurrent changes to the default wait for each other.

        A change that read a template another transaction has since changed
        fails with a serialization error and is retried.
        """
        self.env.cr.execute(SQL("SELECT id FROM %s FOR UPDATE", SQL.identifier(self._table)))

    def _ninthsense_clear_default(self):
        """Clear the default flag on every template except these, before one of these takes it."""
        others = self.with_context(active_test=False).search(
            [("is_default", "=", True), ("id", "not in", self.ids)]
        )
        if others:
            super(OnboardingTemplate, others).write({"is_default": False})
            others.flush_recordset(["is_default"])

    def _ninthsense_check_default_can_go(self):
        """Refuse to disable or delete the default while another template stays enabled."""
        defaults = self.filtered("is_default")
        if not defaults:
            return
        others = self.search_count([("active", "=", True), ("id", "not in", self.ids)])
        if others:
            raise ValidationError(
                self.env._(
                    "The default template cannot be disabled or deleted while other "
                    "templates are enabled. Make another template the default first."
                )
            )

    def _ninthsense_settle_default(self, enabled):
        """Keep exactly one enabled default after these templates were written.

        When no enabled template is the default, the first of `enabled`, the
        templates just created or enabled, becomes the default.
        """
        for template in self:
            if template.is_default and not template.active:
                raise ValidationError(self.env._("A disabled template cannot be the default."))
        if self.search_count([("active", "=", True), ("is_default", "=", True)]):
            return
        first = enabled.filtered("active")[:1]
        if first:
            super(OnboardingTemplate, first).write({"is_default": True})
        elif self.search_count([("active", "=", True)]):
            raise ValidationError(
                self.env._("One enabled template must be the default. Mark one as the default.")
            )


class OnboardingTemplateLine(models.Model):
    _name = "ninthsense.onboarding.template.line"
    _description = "Onboarding Template Document"
    _order = "sequence, id"

    template_id = fields.Many2one(
        "ninthsense.onboarding.template", required=True, ondelete="cascade", index=True
    )
    sequence = fields.Integer()
    document_type_id = fields.Many2one(
        "ninthsense.onboarding.document.type", required=True, ondelete="restrict"
    )
    mandatory = fields.Boolean()
    accept_pdf = fields.Boolean()
    accept_jpg = fields.Boolean()
    accept_png = fields.Boolean()
    accept = fields.Char(compute="_compute_accept", store=True)
    max_mb = fields.Integer(default=3)

    _type_unique = models.Constraint(
        "UNIQUE(template_id, document_type_id)",
        "A document type is listed more than once in the template.",
    )

    @api.depends("accept_pdf", "accept_jpg", "accept_png")
    def _compute_accept(self):
        for line in self:
            parts = []
            if line.accept_pdf:
                parts.append(".pdf")
            if line.accept_jpg:
                parts.append(".jpg,.jpeg")
            if line.accept_png:
                parts.append(".png")
            line.accept = ",".join(parts)

    @api.constrains("accept_pdf", "accept_jpg", "accept_png", "max_mb")
    def _check_limits(self):
        cap = DEFAULT_LIMITS.file_max_mb
        for line in self:
            name = line.document_type_id.display_name
            if not (line.accept_pdf or line.accept_jpg or line.accept_png):
                raise ValidationError(self.env._("%s must accept at least one file type.", name))
            if not MIN_FILE_MB <= line.max_mb <= cap:
                raise ValidationError(
                    self.env._(
                        "%(name)s: the size limit must be between %(low)s and %(high)s MB.",
                        name=name,
                        low=MIN_FILE_MB,
                        high=cap,
                    )
                )

    @api.constrains("document_type_id", "template_id")
    def _check_template_mapping(self):
        _check_now_or_after_save(self.template_id)

    def write(self, vals):
        previous = self.template_id if "template_id" in vals else None
        result = super().write(vals)
        if previous:
            _check_now_or_after_save(previous)
        return result

    def unlink(self):
        templates = self.template_id
        result = super().unlink()
        _check_now_or_after_save(templates)
        return result


class OnboardingTemplateMapping(models.Model):
    _name = "ninthsense.onboarding.template.mapping"
    _description = "Onboarding Template Field Mapping"
    _order = "id"

    template_id = fields.Many2one(
        "ninthsense.onboarding.template", required=True, ondelete="cascade", index=True
    )
    field_key = fields.Selection(FIELD_KEY_SELECTION, string="Field", required=True)
    source_type_id = fields.Many2one(
        "ninthsense.onboarding.document.type",
        string="Source",
        required=True,
        ondelete="restrict",
        domain="[('id', 'in', allowed_type_ids)]",
    )
    fallback_type_id = fields.Many2one(
        "ninthsense.onboarding.document.type",
        string="Fallback",
        ondelete="restrict",
        domain="[('id', 'in', allowed_type_ids)]",
    )
    allowed_type_ids = fields.Many2many(
        "ninthsense.onboarding.document.type", compute="_compute_allowed_type_ids"
    )

    @api.depends("field_key", "template_id.line_ids.document_type_id")
    def _compute_allowed_type_ids(self):
        for row in self:
            types = row.template_id.line_ids.document_type_id
            codes = set(mapping_rules.allowed_sources(row.field_key, types.mapped("code")))
            row.allowed_type_ids = types.filtered(
                lambda doc_type, codes=codes: doc_type.code in codes
            )

    @api.constrains("field_key", "source_type_id", "fallback_type_id", "template_id")
    def _check_template_mapping(self):
        _check_now_or_after_save(self.template_id)
