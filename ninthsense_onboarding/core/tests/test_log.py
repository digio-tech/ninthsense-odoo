import logging
import unittest

from core import log


class TestLog(unittest.TestCase):
    def test_event_carries_name_outcome_and_correlation_id(self):
        with self.assertLogs("odoo.addons.ninthsense_onboarding", level="INFO") as captured:
            log.event(
                "request.link_sent",
                outcome="ok",
                correlation_id="abc-123",
                status="link_sent",
            )
        message = captured.records[0].getMessage()
        self.assertIn('"event": "request.link_sent"', message)
        self.assertIn('"outcome": "ok"', message)
        self.assertIn('"correlation_id": "abc-123"', message)
        self.assertIn('"status": "link_sent"', message)

    def test_disallowed_keys_are_dropped(self):
        with self.assertLogs("odoo.addons.ninthsense_onboarding", level="INFO") as captured:
            log.event("request.link_sent", outcome="ok", not_allowed="super-secret-value")
        message = captured.records[0].getMessage()
        self.assertNotIn("not_allowed", message)
        self.assertNotIn("super-secret-value", message)

    def test_value_for_disallowed_key_never_appears(self):
        with self.assertLogs("odoo.addons.ninthsense_onboarding", level="INFO") as captured:
            log.event(
                "request.link_sent",
                outcome="ok",
                status="link_sent",
                candidate_name="Priya Raghavan",
            )
        message = captured.records[0].getMessage()
        self.assertIn('"status": "link_sent"', message)
        self.assertNotIn("candidate_name", message)
        self.assertNotIn("Priya Raghavan", message)

    def test_email_name_and_aadhaar_values_never_appear(self):
        with self.assertLogs("odoo.addons.ninthsense_onboarding", level="INFO") as captured:
            log.event(
                "request.verified",
                outcome="ok",
                request_id=7,
                email="priya@example.com",
                legal_name="Priya Raghavan",
                aadhaar_number="2345 6789 0123",
            )
        message = captured.records[0].getMessage()
        self.assertIn('"request_id": 7', message)
        for leaked in ("priya@example.com", "Priya Raghavan", "2345 6789 0123", "email"):
            self.assertNotIn(leaked, message)

    def test_only_allow_listed_keys_are_emitted(self):
        with self.assertLogs("odoo.addons.ninthsense_onboarding", level="INFO") as captured:
            log.event("x", outcome="ok", **dict.fromkeys(log.ALLOWED_KEYS, 1), extra=2)
        message = captured.records[0].getMessage()
        self.assertNotIn("extra", message)
        for key in log.ALLOWED_KEYS:
            self.assertIn(f'"{key}"', message)


TOKEN = "mmc-MQCiewmQaDanCrD4brZe_DEKYpZ3AqLXFLvVzho"
PORTAL_PATH = "/api/method/ninthsense.document_collection.portal_api.get_request"


def _access_record(path):
    """A record shaped like the one Odoo's HTTP server logs for each request."""
    line = f'127.0.0.1 - - [01/Jan/2026 00:00:00] "GET {path} HTTP/1.1" 200 12'
    record = logging.LogRecord(
        name=log.ACCESS_LOGGER_NAME,
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=line,
        args=(),
        exc_info=None,
    )
    record.colored_message = f"\x1b[1m{line}\x1b[0m"
    record.http_request_line = f"GET {path} HTTP/1.1"
    return record


class TestTokenRedactingFilter(unittest.TestCase):
    def test_redacts_the_token_from_every_formatted_copy(self):
        record = _access_record(f"{PORTAL_PATH}?token={TOKEN}&x=1")

        self.assertTrue(log.TokenRedactingFilter().filter(record))

        for text in (record.getMessage(), record.colored_message, record.http_request_line):
            self.assertNotIn(TOKEN, text)
            self.assertIn("token=***&x=1", text)

    def test_leaves_an_unrelated_route_untouched(self):
        record = _access_record(f"/web/login?token={TOKEN}")
        original = (record.getMessage(), record.colored_message, record.http_request_line)

        log.TokenRedactingFilter().filter(record)

        self.assertEqual(
            (record.getMessage(), record.colored_message, record.http_request_line), original
        )

    def test_install_adds_the_filter_once(self):
        logger = log.access_logger()
        self.assertEqual(logger.name, "odoo.http.server")
        original_filters = list(logger.filters)
        self.addCleanup(lambda: setattr(logger, "filters", original_filters))
        logger.filters = [
            existing
            for existing in original_filters
            if not isinstance(existing, log.TokenRedactingFilter)
        ]
        before = len(logger.filters)

        log.install_token_filter()
        log.install_token_filter()

        self.assertEqual(len(logger.filters), before + 1)


def _raise_with_personal_data():
    raise ValueError("Priya Raghavan 2345 6789 0123")


class TestWhere(unittest.TestCase):
    def test_names_the_raising_frame_and_nothing_of_the_message(self):
        try:
            _raise_with_personal_data()
        except ValueError as error:
            located = log.where(error)

        module, function, line = located.split(":")
        self.assertEqual(module, __name__)
        self.assertEqual(function, "_raise_with_personal_data")
        self.assertEqual(int(line), _raise_with_personal_data.__code__.co_firstlineno + 1)
        self.assertNotIn("Priya", located)

    def test_an_error_never_raised_has_no_frame(self):
        self.assertIsNone(log.where(ValueError("x")))

    def test_where_is_an_allowed_key(self):
        with self.assertLogs("odoo.addons.ninthsense_onboarding", level="INFO") as captured:
            log.event("portal_call", outcome="server_error", where="a.b:c:1")
        self.assertIn('"where": "a.b:c:1"', captured.records[0].getMessage())


class TestNewCorrelationId(unittest.TestCase):
    def test_reuses_a_well_formed_inbound_id(self):
        self.assertEqual(log.new_correlation_id("abc-123.DEF_456"), "abc-123.DEF_456")

    def test_replaces_a_malformed_inbound_id(self):
        generated = log.new_correlation_id("has a space")
        self.assertNotEqual(generated, "has a space")
        self.assertEqual(len(generated), 36)

    def test_generates_one_when_missing(self):
        self.assertIsNotNone(log.new_correlation_id(None))
