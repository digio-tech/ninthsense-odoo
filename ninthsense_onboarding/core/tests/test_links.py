import datetime
import hashlib
import unittest

from core import links
from core.errors import InvalidToken
from core.limits import DEFAULT_LIMITS


class TestMintAndHashToken(unittest.TestCase):
    def test_minted_token_is_url_safe(self):
        token = links.mint_token()
        self.assertRegex(token, r"^[A-Za-z0-9_-]+$")

    def test_hash_matches_sha256_hex(self):
        token = links.mint_token()
        self.assertEqual(links.hash_token(token), hashlib.sha256(token.encode("utf-8")).hexdigest())


class TestParseToken(unittest.TestCase):
    def test_accepts_a_well_formed_token(self):
        token = "abc-123_XYZ"
        self.assertEqual(links.parse_token(token, DEFAULT_LIMITS), token)

    def test_rejects_a_token_over_the_max_length(self):
        token = "a" * (DEFAULT_LIMITS.token_max_length + 1)
        with self.assertRaises(InvalidToken):
            links.parse_token(token, DEFAULT_LIMITS)

    def test_rejects_characters_outside_the_allowed_set(self):
        with self.assertRaises(InvalidToken):
            links.parse_token("has a space", DEFAULT_LIMITS)

    def test_rejects_an_empty_token(self):
        with self.assertRaises(InvalidToken):
            links.parse_token("", DEFAULT_LIMITS)


class TestPortalState(unittest.TestCase):
    def setUp(self):
        self.now = datetime.datetime(2026, 1, 15, tzinfo=datetime.UTC)
        self.future = self.now + datetime.timedelta(days=1)
        self.past = self.now - datetime.timedelta(days=1)

    def test_link_sent_before_expiry_is_open(self):
        self.assertEqual(links.portal_state("link_sent", self.future, self.now), "open")

    def test_link_sent_past_expiry_is_expired(self):
        self.assertEqual(links.portal_state("link_sent", self.past, self.now), "expired")

    def test_link_sent_without_expiry_is_open(self):
        self.assertEqual(links.portal_state("link_sent", None, self.now), "open")

    def test_data_received_is_submitted_even_past_expiry(self):
        self.assertEqual(links.portal_state("data_received", self.past, self.now), "submitted")

    def test_completed_and_cancelled_are_revoked(self):
        for state in ("completed", "cancelled"):
            self.assertEqual(links.portal_state(state, self.future, self.now), "revoked")


class TestExpiry(unittest.TestCase):
    def test_expiry_adds_the_given_days(self):
        now = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
        self.assertEqual(links.expiry(now, 30), now + datetime.timedelta(days=30))


if __name__ == "__main__":
    unittest.main()
