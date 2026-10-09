import datetime
import json
import time
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import ConcurrencyError
from odoo.tests import HttpCase, tagged
from werkzeug.datastructures import FileStorage

from ..controllers.portal import validators
from ..core import portal_contract
from ..core.errors import InvalidPayload
from ..core.links import hash_token
from ..services import storage
from .portal_helpers import (
    MB,
    PDF_BYTES,
    PNG_BYTES,
    PREFIX,
    SECRET,
    completion_document,
    completion_payload,
    envelope,
    send_link,
    signed_headers,
)
from .test_send import hired_applicant

AADHAAR_EXTRACTED = {
    "name": "Priya Raghavan",
    "gender": "F",
    "date_of_birth": "1997-11-09",
    "aadhaar_number": "2345 6789 0123",
}
PAN_EXTRACTED = {"name": "Priya Raghavan", "pan_number": "abcpr1234f"}
LOGGER = "odoo.addons.ninthsense"


def _fail_with_personal_data(*args, **kwargs):
    raise RuntimeError("Priya Raghavan 2345 6789 0123")


def _events(captured):
    return [json.loads(line.split(":", 2)[2]) for line in captured.output]


@tagged("post_install", "-at_install")
class TestPortalApi(HttpCase):
    def setUp(self):
        super().setUp()
        applicant = hired_applicant(
            self.env, {"partner_name": "Priya Raghavan", "email_from": "priya.portal@example.test"}
        )
        self.request_record, self.token = send_link(self.env, applicant)

    # ------------------------------------------------------------------ helpers

    def _open(self, route, **kwargs):
        response = self.url_open(PREFIX + route, **kwargs)
        self.env.invalidate_all()
        return response

    def _get(self, token=None):
        return self._open("get_request", params={"token": token or self.token})

    def _store(self, code, doc_id, name="card.png", content=PNG_BYTES, token=None):
        return self._open(
            "store_document",
            files={
                "token": (None, token or self.token),
                "document_code": (None, code),
                "verification_document_id": (None, doc_id),
                "file": (name, content, "application/octet-stream"),
            },
        )

    def _discard(self, doc_id, token=None):
        return self._open(
            "discard_document",
            files={
                "token": (None, token or self.token),
                "verification_document_id": (None, doc_id),
            },
        )

    def _complete(self, payload, token=None, headers=None):
        raw = envelope(token or self.token, payload)
        return raw, self._open(
            "store_verification", data=raw, headers=headers or signed_headers(raw)
        )

    def _payload(self, documents=None):
        if documents is None:
            documents = [
                completion_document("aadhaar_front", "doc_a", AADHAAR_EXTRACTED),
                completion_document("pan_card", "doc_p", PAN_EXTRACTED),
            ]
        return completion_payload(self.request_record, documents)

    def _assert_error(self, response, status, code):
        self.assertEqual(response.status_code, status, response.text)
        self.assertEqual(response.json(), {"error": {"code": code}})

    def _held(self):
        return sorted(self.request_record.document_ids.mapped("verification_document_id"))

    def _set_state(self, state):
        self.request_record.sudo().write({"state": state})

    def _expire(self):
        self.request_record.link_expires_at = fields.Datetime.now() - datetime.timedelta(days=1)

    # ------------------------------------------------------------- get_request

    def test_get_open_descriptor(self):
        response = self._get()

        self.assertEqual(response.status_code, 200, response.text)
        descriptor = response.json()
        portal_contract.validate_descriptor(validators(), descriptor)
        self.assertEqual(descriptor["state"], "open")
        self.assertEqual(descriptor["ref"], self.request_record.ref)
        self.assertEqual(descriptor["goal_key"], "onboarding")
        self.assertEqual(descriptor["stage"], "Onboarding")
        self.assertEqual(descriptor["hrms"]["system"], "odoo")
        self.assertEqual(descriptor["hrms"]["instance"], self.base_url())
        self.assertEqual(descriptor["subject"], {"display_name": "Priya"})
        self.assertEqual(descriptor["branding"]["org_name"], self.env.company.name)
        self.assertTrue(descriptor["expires_at"].endswith("Z"))
        documents = descriptor["steps"][0]["documents"]
        self.assertEqual(
            [document["document_code"] for document in documents],
            [line.code for line in self.request_record.line_ids],
        )
        self.assertEqual(documents[0]["max_bytes"], 3 * MB)
        self.assertEqual(documents[3]["accept"], [".pdf"])
        self.assertEqual(descriptor["completion"]["callback_path"], PREFIX + "store_verification")

    def test_get_shows_the_stored_document_on_its_line(self):
        self._store("pan_card", "doc_p")

        documents = self._get().json()["steps"][0]["documents"]

        filled = {d["document_code"]: d.get("verification_document_id") for d in documents}
        self.assertEqual(filled["pan_card"], "doc_p")
        self.assertIsNone(filled["aadhaar_front"])

    def test_get_submitted_descriptor_carries_no_documents(self):
        self._set_state("data_received")

        response = self._get()

        self.assertEqual(response.status_code, 200, response.text)
        descriptor = response.json()
        portal_contract.validate_descriptor(validators(), descriptor)
        self.assertEqual(descriptor["state"], "submitted")
        self.assertEqual(descriptor["steps"][0]["documents"], [])

    def test_get_with_a_link_that_does_not_resolve_is_not_found(self):
        old_token = self.token
        _request, new_token = send_link(self.env, self.request_record.applicant_id)

        for label, token in (
            ("unknown", "unknown-token"),
            ("bad characters", "bad$token"),
            ("too long", "a" * 129),
            ("replaced", old_token),
        ):
            with self.subTest(label):
                self._assert_error(self._get(token), 404, "invalid_token")
        self.assertEqual(self._get(new_token).status_code, 200)

    def test_get_expired_link_is_not_found(self):
        self._expire()

        self._assert_error(self._get(), 404, "invalid_token")

    def test_get_for_completed_and_cancelled_requests_is_not_found(self):
        for state in ("completed", "cancelled"):
            with self.subTest(state):
                self.request_record.sudo().write(
                    {"state": state, "link_hash": hash_token(self.token)}
                )
                self._assert_error(self._get(), 404, "invalid_token")

    # ----------------------------------------------------------- store_document

    def test_store_document(self):
        response = self._store("aadhaar_front", "doc_a")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"ok": True})
        document = self.request_record.document_ids
        self.assertEqual(document.code, "aadhaar_front")
        self.assertEqual(document.verification_document_id, "doc_a")
        self.assertTrue(document.received_at)
        attachment = document.attachment_id.sudo()
        self.assertEqual(attachment.name, "card.png")
        self.assertEqual(attachment.raw.content, PNG_BYTES)
        self.assertEqual(attachment.res_model, "ninthsense.onboarding.request")
        self.assertEqual(attachment.res_id, self.request_record.id)
        self.assertFalse(attachment.public)

    def test_store_document_accepts_a_pdf_where_pdf_is_listed(self):
        response = self._store("resume", "doc_r", "cv.pdf", PDF_BYTES)

        self.assertEqual(response.status_code, 200, response.text)

    def test_store_the_same_id_again_replaces_the_document(self):
        self._store("aadhaar_front", "doc_a")
        first = self.request_record.document_ids.attachment_id

        response = self._store("aadhaar_front", "doc_a", content=PNG_BYTES + b"1")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(self.request_record.document_ids), 1)
        self.assertFalse(first.exists())
        self.assertEqual(
            self.request_record.document_ids.attachment_id.raw.content, PNG_BYTES + b"1"
        )

    def test_a_new_id_on_a_held_line_replaces_its_document(self):
        self._store("aadhaar_front", "doc_a")
        self._store("pan_card", "doc_p")
        first = self.request_record.document_ids.filtered(
            lambda document: document.code == "aadhaar_front"
        ).attachment_id

        response = self._store("aadhaar_front", "doc_b", content=PNG_BYTES + b"2")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self._held(), ["doc_b", "doc_p"])
        self.assertFalse(first.exists())
        held = self.request_record.document_ids.filtered(
            lambda document: document.code == "aadhaar_front"
        )
        self.assertEqual(held.attachment_id.raw.content, PNG_BYTES + b"2")

    def test_repeated_uploads_to_one_line_keep_one_file(self):
        for index in range(5):
            self._store("aadhaar_front", f"doc_{index}", content=PNG_BYTES + bytes([index]))

        self.assertEqual(self._held(), ["doc_4"])
        attachments = (
            self.env["ir.attachment"]
            .sudo()
            .search(
                [
                    ("res_model", "=", "ninthsense.onboarding.request"),
                    ("res_id", "=", self.request_record.id),
                ]
            )
        )
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments.raw.content, PNG_BYTES + bytes([4]))

    def test_store_unknown_document_code(self):
        self._assert_error(self._store("driving_license", "doc_x"), 400, "unknown_document")
        self.assertFalse(self.request_record.document_ids)

    def test_store_rejects_files_the_line_does_not_accept(self):
        cases = (
            ("wrong extension", "resume", "cv.png", PNG_BYTES),
            ("content not matching", "aadhaar_front", "card.png", b"plain text, not an image"),
            ("over the size limit", "aadhaar_front", "card.png", PNG_BYTES + b"0" * (3 * MB)),
        )
        for label, code, name, content in cases:
            with self.subTest(label):
                self._assert_error(
                    self._store(code, "doc_x", name, content), 415, "file_type_not_allowed"
                )
        self.assertFalse(self.request_record.document_ids)

    def test_store_malformed_document_id(self):
        for doc_id in ("", "x" * 257):
            with self.subTest(len(doc_id)):
                self._assert_error(self._store("pan_card", doc_id), 400, "invalid_payload")

    def test_store_when_the_request_is_not_open(self):
        self._store("aadhaar_front", "doc_a")
        for label, change in (
            ("data received", lambda: self._set_state("data_received")),
            ("expired", lambda: (self._set_state("link_sent"), self._expire())),
            ("completed", lambda: self._set_state("completed")),
            ("cancelled", lambda: self._set_state("cancelled")),
        ):
            with self.subTest(label):
                change()
                self.request_record.sudo().link_hash = hash_token(self.token)
                self._assert_error(self._store("pan_card", "doc_p"), 404, "invalid_token")
        self.assertEqual(self._held(), ["doc_a"])

    # --------------------------------------------------------- discard_document

    def test_discard_document(self):
        self._store("aadhaar_front", "doc_a")
        attachment = self.request_record.document_ids.attachment_id

        response = self._discard("doc_a")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"ok": True})
        self.assertFalse(self.request_record.document_ids)
        self.assertFalse(attachment.exists())

    def test_discard_an_id_nothing_holds(self):
        self.assertEqual(self._discard("doc_z").status_code, 200)

    def test_discard_when_the_request_is_not_open(self):
        self._store("aadhaar_front", "doc_a")
        self._set_state("data_received")

        self._assert_error(self._discard("doc_a"), 404, "invalid_token")
        self.assertEqual(self._held(), ["doc_a"])

        self._set_state("link_sent")
        self._expire()
        self._assert_error(self._discard("doc_a"), 404, "invalid_token")

        for state in ("completed", "cancelled"):
            self._set_state(state)
            self.request_record.sudo().link_hash = hash_token(self.token)
            self._assert_error(self._discard("doc_a"), 404, "invalid_token")
        self.assertEqual(self._held(), ["doc_a"])

    # ------------------------------------------------------- store_verification

    def test_completion_with_a_bad_signature(self):
        raw = envelope(self.token, self._payload())
        cases = (
            ("missing", {"Content-Type": "application/json"}),
            ("malformed header", {"Content-Type": "application/json", "X-Portal-Signature": "x"}),
            ("stale", signed_headers(raw, timestamp=int(time.time()) - 1000)),
            ("from the future", signed_headers(raw, timestamp=int(time.time()) + 1000)),
            ("wrong secret", signed_headers(raw, secret="w" * 40)),
        )
        for label, headers in cases:
            with self.subTest(label):
                response = self._open("store_verification", data=raw, headers=headers)
                self._assert_error(response, 401, "bad_signature")
        self.assertEqual(self.request_record.state, "link_sent")

    def test_completion_with_an_unknown_token(self):
        _raw, response = self._complete(self._payload(), token="unknown-token")

        self._assert_error(response, 404, "invalid_token")

    def test_completion_that_fails_the_schema(self):
        payload = self._payload()
        payload["steps"][0]["documents"][0]["extra"] = 1

        _raw, response = self._complete(payload)

        self._assert_error(response, 400, "invalid_payload")
        self.assertEqual(self.request_record.state, "link_sent")

    def test_completion_that_is_not_json(self):
        raw = b"not json"
        response = self._open("store_verification", data=raw, headers=signed_headers(raw))

        self._assert_error(response, 400, "invalid_payload")

    def test_completion_for_another_ref(self):
        payload = self._payload()
        payload["ref"] = "ONB-2000-9999"

        _raw, response = self._complete(payload)

        self._assert_error(response, 400, "invalid_payload")
        self.assertEqual(self.request_record.state, "link_sent")
        self.assertFalse(self.request_record.received_at)

    def test_completion_moves_the_request_to_data_received(self):
        self._store("aadhaar_front", "doc_a")
        self._store("pan_card", "doc_p")

        payload = self._payload(
            [
                completion_document("aadhaar_front", "doc_a", AADHAAR_EXTRACTED),
                completion_document("pan_card", "doc_p", dict(PAN_EXTRACTED, name="Priya R")),
            ]
        )
        raw, response = self._complete(payload)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"ok": True})
        record = self.request_record
        self.assertEqual(record.state, "data_received")
        self.assertTrue(record.received_at)
        self.assertEqual(self._held(), ["doc_a", "doc_p"])
        values = {(value.field_key, value.source_code): value.value for value in record.value_ids}
        self.assertEqual(values["aadhaar_number", "aadhaar_front"], "XXXX XXXX 0123")
        self.assertEqual(values["legal_name", "aadhaar_front"], "Priya Raghavan")
        self.assertEqual(values["legal_name", "pan_card"], "Priya R")
        self.assertEqual(values["pan_number", "pan_card"], "ABCPR1234F")
        self.assertNotIn("2345 6789 0123", record.results_raw)
        self.assertIn("XXXX XXXX 0123", record.results_raw)
        self.assertNotIn(self.token, record.results_raw)

    def test_a_second_bundle_replaces_values_and_deletes_unnamed_documents(self):
        self._store("aadhaar_front", "doc_a")
        self._store("pan_card", "doc_p")
        self._complete(self._payload())
        first_values = self.request_record.value_ids

        second = self._payload(
            [
                completion_document(
                    "pan_card", "doc_p", {"name": "Priya R", "pan_number": "ZZZPR9999Z"}
                )
            ]
        )
        _raw, response = self._complete(second)

        self.assertEqual(response.status_code, 200, response.text)
        record = self.request_record
        self.assertEqual(record.state, "data_received")
        self.assertEqual(self._held(), ["doc_p"])
        self.assertFalse(first_values.exists())
        values = {(value.field_key, value.source_code): value.value for value in record.value_ids}
        self.assertEqual(
            values,
            {("legal_name", "pan_card"): "Priya R", ("pan_number", "pan_card"): "ZZZPR9999Z"},
        )

    def test_a_retried_bundle_leaves_the_same_data(self):
        self._store("aadhaar_front", "doc_a")
        payload = self._payload([completion_document("aadhaar_front", "doc_a", AADHAAR_EXTRACTED)])
        self._complete(payload)
        before = sorted((v.field_key, v.value) for v in self.request_record.value_ids)

        _raw, response = self._complete(payload)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            sorted((v.field_key, v.value) for v in self.request_record.value_ids), before
        )
        self.assertEqual(self._held(), ["doc_a"])

    def test_completion_ignores_unfiled_entries_and_keeps_their_document(self):
        self._store("aadhaar_front", "doc_a")
        documents = [
            completion_document("unfiled", "doc_a", AADHAAR_EXTRACTED),
            completion_document("unfiled", "doc_unknown", {"name": "Someone"}),
            completion_document("pan_card", "doc_p", PAN_EXTRACTED),
        ]

        _raw, response = self._complete(self._payload(documents))

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self._held(), ["doc_a"])
        values = {value.field_key: value.value for value in self.request_record.value_ids}
        self.assertNotIn("aadhaar_number", values)
        self.assertEqual(values["pan_number"], "ABCPR1234F")

    def test_completion_for_completed_and_cancelled_requests_is_not_found(self):
        for state in ("completed", "cancelled"):
            with self.subTest(state):
                self.request_record.sudo().write(
                    {"state": state, "link_hash": hash_token(self.token)}
                )
                _raw, response = self._complete(self._payload())
                self._assert_error(response, 404, "invalid_token")
        self.assertFalse(self.request_record.received_at)

    def test_completion_is_accepted_after_the_link_expires(self):
        self._expire()

        _raw, response = self._complete(self._payload())

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.request_record.state, "data_received")

    def test_every_error_body_is_the_bare_code(self):
        responses = [
            self._get("unknown-token"),
            self._store("driving_license", "doc_x"),
            self._open(
                "store_verification", data=b"{}", headers=signed_headers(b"{}", SECRET[::-1])
            ),
        ]
        for response in responses:
            self.assertEqual(list(response.json()), ["error"])
            self.assertEqual(list(response.json()["error"]), ["code"])

    # ------------------------------------------------------------ server faults

    def test_a_descriptor_that_fails_its_own_schema_is_a_server_error(self):
        with (
            patch.object(portal_contract, "validate_descriptor", side_effect=InvalidPayload("bad")),
            self.assertLogs(LOGGER, level="INFO") as captured,
        ):
            response = self._get()

        self._assert_error(response, 500, "server_error")
        end = _events(captured)[-1]
        self.assertEqual(end["outcome"], "descriptor_invalid")
        self.assertEqual(end["http_status"], 500)

    def test_an_unexpected_error_is_logged_with_where_it_was_raised_and_no_message(self):
        self._store("aadhaar_front", "doc_a")
        with (
            patch.object(storage, "discard_document", _fail_with_personal_data),
            self.assertLogs(LOGGER, level="INFO") as captured,
        ):
            response = self._discard("doc_a")

        self._assert_error(response, 500, "server_error")
        end = _events(captured)[-1]
        line = _fail_with_personal_data.__code__.co_firstlineno + 1
        self.assertEqual(end["reason_code"], "RuntimeError")
        self.assertEqual(end["where"], f"{__name__}:_fail_with_personal_data:{line}")
        output = "\n".join(captured.output)
        for leaked in ("Priya", "2345 6789 0123"):
            self.assertNotIn(leaked, output)

    def test_a_concurrency_failure_is_left_to_odoo_to_retry(self):
        calls = []
        original = storage.discard_document

        def conflict_once(*args, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                raise ConcurrencyError("concurrent update")
            return original(*args, **kwargs)

        self._store("aadhaar_front", "doc_a")
        with (
            patch.object(storage, "discard_document", conflict_once),
            patch("odoo.http.retrying.random.uniform", return_value=0),
        ):
            response = self._discard("doc_a")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(calls), 2)
        self.assertFalse(self.request_record.document_ids)

    # ---------------------------------------------------------- upload handling

    def test_an_aadhaar_number_in_the_file_name_is_masked(self):
        response = self._store("aadhaar_front", "doc_a", name="aadhaar_234567890123.png")

        self.assertEqual(response.status_code, 200, response.text)
        name = self.request_record.document_ids.attachment_id.sudo().name
        self.assertEqual(name, "aadhaar_XXXX XXXX 0123.png")

    def test_no_more_than_one_byte_over_the_limit_is_read(self):
        sizes = []

        def read(upload, size=-1):
            sizes.append(size)
            return upload.stream.read(size)

        with patch.object(FileStorage, "read", read, create=True):
            response = self._store("aadhaar_front", "doc_a", content=PNG_BYTES + b"0" * (4 * MB))

        self._assert_error(response, 415, "file_type_not_allowed")
        self.assertEqual(sizes, [3 * MB + 1])

    # ----------------------------------------------------------- parsed values

    def test_a_mobile_with_the_country_code_is_kept_usable(self):
        self._store("resume", "doc_r", "cv.pdf", PDF_BYTES)
        documents = [
            completion_document(
                "resume", "doc_r", {"full_name": "Priya Raghavan", "phone": "+91 98765 43210"}
            )
        ]

        _raw, response = self._complete(self._payload(documents))

        self.assertEqual(response.status_code, 200, response.text)
        values = {value.field_key: value.value for value in self.request_record.value_ids}
        self.assertEqual(values["cell_number"], "98765 43210")

    def test_every_aadhaar_spelling_is_masked_in_the_stored_results(self):
        self._store("aadhaar_front", "doc_a")
        payload = self._payload([completion_document("aadhaar_front", "doc_a", AADHAAR_EXTRACTED)])
        payload["steps"][0]["result"] = {
            "remark": "2345  6789 0123",
            "ocr": ["2345.6789.0123", {"aadhaar": 234567890123}],
        }

        _raw, response = self._complete(payload)

        self.assertEqual(response.status_code, 200, response.text)
        stored = self.request_record.results_raw
        for spelling in ("2345  6789 0123", "2345.6789.0123", "234567890123"):
            self.assertNotIn(spelling, stored)
        result = json.loads(stored)["payload"]["steps"][0]["result"]
        self.assertEqual(result["ocr"][1]["aadhaar"], "XXXX XXXX 0123")
