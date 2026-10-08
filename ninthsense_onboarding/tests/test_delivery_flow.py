import re

from odoo.tests import HttpCase, new_test_user, tagged

from .portal_helpers import (
    PDF_BYTES,
    PNG_BYTES,
    PREFIX,
    completion_document,
    completion_payload,
    envelope,
    send_link,
    signed_headers,
)
from .test_send import hired_applicant

AADHAAR_RUN = re.compile(r"\d(?:[ -]?\d){11}")
AADHAAR_NUMBER = "2345 6789 0123"


@tagged("post_install", "-at_install")
class TestDeliveryFlow(HttpCase):
    def _post_documents(self, request, token):
        for line in request.line_ids.filtered("mandatory"):
            pdf_only = line.accept == ".pdf"
            response = self.url_open(
                PREFIX + "store_document",
                files={
                    "token": (None, token),
                    "document_code": (None, line.code),
                    "verification_document_id": (None, f"doc_{line.code}"),
                    "file": (
                        "scan.pdf" if pdf_only else "scan.png",
                        PDF_BYTES if pdf_only else PNG_BYTES,
                        "application/octet-stream",
                    ),
                },
            )
            self.assertEqual(response.status_code, 200, response.text)

    def _rpc(self, model, method, *args, **kwargs):
        response = self.url_open(
            "/web/dataset/call_kw",
            json={"params": {"model": model, "method": method, "args": args, "kwargs": kwargs}},
        )
        body = response.json()
        self.assertNotIn("error", body, body)
        return body["result"]

    def test_candidate_delivery_reaches_the_request_without_a_full_aadhaar_number(self):
        applicant = hired_applicant(
            self.env, {"partner_name": "Priya Raghavan", "email_from": "priya.flow@example.test"}
        )
        request, token = send_link(self.env, applicant)

        descriptor = self.url_open(PREFIX + "get_request", params={"token": token}).json()
        self.assertEqual(descriptor["state"], "open")
        self._post_documents(request, token)

        mandatory = request.line_ids.filtered("mandatory")
        documents = [
            completion_document(
                line.code,
                f"doc_{line.code}",
                {"aadhaar_number": AADHAAR_NUMBER, "name": "Priya Raghavan"}
                if line.code == "aadhaar_front"
                else {"name": f"Priya Raghavan {AADHAAR_NUMBER}"},
            )
            for line in mandatory
        ]
        payload = completion_payload(request, documents)
        payload["steps"][0]["result"] = {"remark": f"Aadhaar {AADHAAR_NUMBER.replace(' ', '')}"}
        raw = envelope(token, payload)
        response = self.url_open(
            PREFIX + "store_verification", data=raw, headers=signed_headers(raw)
        )
        self.assertEqual(response.status_code, 200, response.text)

        officer = new_test_user(
            self.env,
            login="onb_officer",
            groups="base.group_user,hr_recruitment.group_hr_recruitment_user",
        )
        self.authenticate(officer.login, officer.login)
        record = self._rpc(
            "ninthsense.onboarding.request",
            "read",
            [request.id],
            ["state", "results_raw", "document_ids", "value_ids"],
        )[0]

        self.assertEqual(record["state"], "data_received")
        stored = self._rpc(
            "ninthsense.onboarding.document", "read", record["document_ids"], ["code"]
        )
        self.assertEqual({d["code"] for d in stored}, set(mandatory.mapped("code")))
        values = self._rpc(
            "ninthsense.onboarding.value", "read", record["value_ids"], ["field_key", "value"]
        )
        by_key = {value["field_key"]: value["value"] for value in values}
        self.assertEqual(by_key["aadhaar_number"], "XXXX XXXX 0123")
        self.assertTrue(by_key["legal_name"])
        self.assertIn("XXXX XXXX 0123", record["results_raw"])
        self.assertIsNone(AADHAAR_RUN.search(record["results_raw"]))
        for value in values:
            self.assertIsNone(AADHAAR_RUN.search(value["value"]), msg=value["field_key"])
