import json
import time

from odoo.tests import HttpCase, new_test_user, tagged

from .portal_helpers import PREFIX, post_documents, post_verification, send_link
from .test_create_employee import OFFICER_GROUPS
from .test_send import PORTAL_URL, SECRET, hired_applicant

LOGGER = "odoo.addons.ninthsense"
EMAIL = "priya.log@example.test"
NAME = "Priya Raghavan"
ACCOUNT_NUMBER = "50100247731902"
ACCESS_LOGGER = "odoo.http.server"


@tagged("post_install", "-at_install")
class TestLogPrivacy(HttpCase):
    def test_the_flow_logs_no_personal_value_and_brackets_every_portal_call(self):
        applicant = hired_applicant(self.env, {"partner_name": NAME, "email_from": EMAIL})
        with self.assertLogs(LOGGER, level="DEBUG") as captured:
            request, token = send_link(self.env, applicant)
            link_hash = request.sudo().link_hash
            post_documents(self, request, token)
            post_verification(
                self,
                request,
                token,
                {
                    "aadhaar_front": {"aadhaar_number": "2345 6789 0123", "name": NAME},
                    "pan_card": {"name": NAME, "pan_number": "ABCPR1234F"},
                },
            )
            self.env.invalidate_all()
            officer = new_test_user(self.env, login="onb_log_officer", groups=OFFICER_GROUPS)
            applicant.with_user(officer).create_employee_from_applicant()

        output = "\n".join(captured.output)
        for secret in (
            token,
            link_hash,
            EMAIL,
            NAME,
            "Raghavan",
            "ABCPR1234F",
            "2345 6789 0123",
            "234567890123",
            ACCOUNT_NUMBER,
            PORTAL_URL,
            SECRET,
        ):
            self.assertNotIn(secret, output)

        events = [json.loads(line.split(":", 2)[2]) for line in captured.output]
        calls = {}
        for entry in events:
            if entry["event"] == "portal_call":
                calls.setdefault(entry["correlation_id"], []).append(entry["outcome"])
        self.assertEqual(len(calls), len(request.line_ids.filtered("mandatory")) + 1, calls)
        for correlation_id, outcomes in calls.items():
            self.assertEqual(outcomes[0], "start", correlation_id)
            self.assertEqual(len(outcomes), 2, correlation_id)
            self.assertEqual(outcomes[1], "ok", correlation_id)
        self.assertIn("request_completed", {entry["event"] for entry in events})

    def test_the_access_log_never_carries_the_link_token(self):
        applicant = hired_applicant(
            self.env, {"partner_name": NAME, "email_from": "priya.access@example.test"}
        )
        _request, token = send_link(self.env, applicant)

        with self.assertLogs(ACCESS_LOGGER, level="INFO") as captured:
            response = self.url_open(PREFIX + "get_request", params={"token": token})
            # The server logs the request line once the body is sent, so after the reply.
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and not any(
                "get_request" in record.getMessage() for record in captured.records
            ):
                time.sleep(0.05)

        self.assertEqual(response.status_code, 200, response.text)
        records = [record for record in captured.records if "get_request" in record.getMessage()]
        self.assertTrue(records)
        for record in records:
            for text in (
                record.getMessage(),
                getattr(record, "colored_message", ""),
                getattr(record, "http_request_line", ""),
            ):
                self.assertNotIn(token, text)
        self.assertIn("token=***", records[0].getMessage())
