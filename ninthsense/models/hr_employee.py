from odoo import fields, models
from odoo.fields import Command
from odoo.tools import plaintext2html
from odoo.tools.misc import clean_context

from ..core import fill, log
from ..services import employee_fill

_RESUME_TYPE_XMLIDS = {
    "education": "hr_skills.resume_type_education",
    "experience": "hr_skills.resume_type_experience",
}


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    def _ninthsense_complete_request(self, request):
        """Complete `request` for this new employee, which its data filled.

        Creates the bank account and resume lines from the values the request
        template's mapping chooses, attaches the request's documents, and
        appends what it created or failed to attach to the fill report.
        """
        self.ensure_one()
        request = request.sudo()
        employee = self.with_context(clean_context(self.env.context))
        result = fill.build({}, employee_fill.chosen_values(request), {}, {})
        created = []
        if result.bank:
            created.append(employee._ninthsense_bank_account(result.bank))
        created.extend(employee._ninthsense_resume_lines(result.resume_lines))
        created = [row for row in created if row]
        created.extend(employee._ninthsense_copy_documents(request))

        next_sequence = max(request.fill_line_ids.mapped("sequence"), default=-1) + 1
        self.env["ninthsense.onboarding.fill.line"].sudo().create(
            [
                dict(row, request_id=request.id, sequence=next_sequence + index)
                for index, row in enumerate(created)
            ]
        )
        request.write(
            {
                "employee_id": self.id,
                "completed_at": fields.Datetime.now(),
                "state": "completed",
                "link_hash": False,
            }
        )
        log.event("request_completed", outcome="ok", request_id=request.id, state="completed")

    def _ninthsense_bank_account(self, bank):
        """The bank account on the work contact, unless that contact already holds the number."""
        partner = self.work_contact_id
        if not partner:
            return None
        Bank = self.env["res.partner.bank"]
        account = Bank.search(
            [("partner_id", "=", partner.id), ("account_number", "=", bank["account_number"])],
            limit=1,
        )
        row = None
        if not account:
            values = dict(bank, partner_id=partner.id)
            if values.get("clearing_number"):
                # Without an Indian label, base shows its generic clearing label instead.
                label = self.env["clearing.label"].search([("country_id.code", "=", "IN")], limit=1)
                if label:
                    values["clearing_label_id"] = label.id
            account = Bank.create(values)
            row = {
                "outcome": "created",
                "label": self.env._("Bank Account"),
                "value": bank["account_number"],
            }
        self.bank_account_ids = [Command.link(account.id)]
        return row

    def _ninthsense_resume_lines(self, lines):
        rows = []
        labels = {
            "education": self.env._("Education"),
            "experience": self.env._("Previous Employment"),
        }
        for line in lines:
            line_type = self.env.ref(
                _RESUME_TYPE_XMLIDS[line["line_type"]], raise_if_not_found=False
            )
            if not line_type:
                rows.append(
                    {
                        "outcome": "skipped_invalid",
                        "label": labels[line["line_type"]],
                        "value": line["name"],
                        "reason": self.env._(
                            "Not created: its resume line type was deleted from Odoo."
                        ),
                    }
                )
                continue
            values = {
                "employee_id": self.id,
                "name": line["name"],
                "line_type_id": line_type.id,
                "description": self._ninthsense_resume_description(line),
            }
            if line.get("date_start"):
                values["date_start"] = line["date_start"]
            self.env["hr.resume.line"].create(values)
            rows.append(
                {"outcome": "created", "label": labels[line["line_type"]], "value": line["name"]}
            )
        return rows

    def _ninthsense_resume_description(self, line):
        details = line.get("details") or {}
        texts = []
        if details.get("percentage"):
            texts.append(self.env._("Percentage: %(value)s", value=details["percentage"]))
        if details.get("designation"):
            texts.append(self.env._("Designation: %(value)s", value=details["designation"]))
        if details.get("total_experience"):
            texts.append(
                self.env._("Total experience: %(value)s", value=details["total_experience"])
            )
        if not line.get("date_start"):
            texts.append(self.env._("Dates not read from documents"))
        return plaintext2html("\n".join(texts))

    def _ninthsense_copy_documents(self, request):
        """Copy each received document to the employee, reporting rather than raising a failure.

        A document whose content the employee already holds, as a copy of an
        applicant attachment for instance, is not copied again.
        """
        rows = []
        labels = {line.code: line.label for line in request.line_ids}
        held = (
            self.env["ir.attachment"]
            .sudo()
            .search([("res_model", "=", self._name), ("res_id", "=", self.id)])
        )
        checksums = set(held.mapped("checksum"))
        for document in request.document_ids:
            attachment = document.attachment_id.sudo()
            if attachment.checksum in checksums:
                continue
            checksums.add(attachment.checksum)
            try:
                with self.env.cr.savepoint():
                    attachment.copy({"res_model": self._name, "res_id": self.id, "public": False})
            except Exception:
                log.event(
                    "attach_failed",
                    outcome="error",
                    request_id=request.id,
                    employee_id=self.id,
                    attachment_id=attachment.id,
                )
                rows.append(
                    {
                        "outcome": "attach_failed",
                        "label": labels.get(document.code) or document.code,
                        "value": attachment.name,
                        "reason": self.env._("The document could not be attached."),
                    }
                )
        return rows
