import unittest

from core import config
from core.errors import NotConfigured

SECRET = "s" * 32


def _parse(url="https://portal.example.com", secret=SECRET, days=None, insecure=False):
    return config.parse(url, secret, days, allow_insecure_localhost=insecure)


class TestPortalUrl(unittest.TestCase):
    def test_https_origin_is_accepted(self):
        self.assertEqual(_parse().portal_url, "https://portal.example.com")

    def test_port_is_kept(self):
        self.assertEqual(
            _parse("https://portal.example.com:8443").portal_url, "https://portal.example.com:8443"
        )

    def test_bare_trailing_slash_is_dropped(self):
        self.assertEqual(
            _parse("https://portal.example.com/").portal_url, "https://portal.example.com"
        )

    def test_path_query_or_fragment_is_rejected(self):
        for url in (
            "https://portal.example.com/app",
            "https://portal.example.com?x=1",
            "https://portal.example.com/#frag",
        ):
            self.assertIsNone(_parse(url).portal_url, msg=url)

    def test_plain_http_is_rejected(self):
        self.assertIsNone(_parse("http://portal.example.com").portal_url)

    def test_http_localhost_needs_the_insecure_flag(self):
        for url in ("http://localhost:3100", "http://127.0.0.1:3100"):
            self.assertIsNone(_parse(url).portal_url, msg=url)
            self.assertEqual(_parse(url, insecure=True).portal_url, url)

    def test_http_localhost_subdomain_needs_the_insecure_flag(self):
        url = "http://odoo.portal.localhost:3400"
        self.assertIsNone(_parse(url).portal_url)
        self.assertEqual(_parse(url, insecure=True).portal_url, url)

    def test_the_insecure_flag_does_not_open_other_hosts(self):
        for url in (
            "http://portal.example.com",
            "http://localhost.example.com",
            "http://notlocalhost",
        ):
            self.assertIsNone(_parse(url, insecure=True).portal_url, msg=url)

    def test_blank_and_missing_are_unset(self):
        for url in (None, "", "   "):
            self.assertIsNone(_parse(url).portal_url)


class TestSecret(unittest.TestCase):
    def test_thirty_two_characters_is_accepted(self):
        self.assertEqual(_parse(secret=SECRET).secret, SECRET)

    def test_shorter_is_unset(self):
        self.assertIsNone(_parse(secret="s" * 31).secret)

    def test_missing_is_unset(self):
        self.assertIsNone(_parse(secret=None).secret)

    def test_secret_is_not_in_the_repr(self):
        self.assertNotIn(SECRET, repr(_parse()))


class TestLinkValidityDays(unittest.TestCase):
    def test_defaults_to_fourteen(self):
        for value in (None, "", "  "):
            self.assertEqual(_parse(days=value).link_validity_days, 14)

    def test_accepts_one_to_ninety(self):
        for value, expected in (("1", 1), (90, 90), ("30", 30)):
            self.assertEqual(_parse(days=value).link_validity_days, expected)

    def test_rejects_anything_else(self):
        for value in ("0", "91", "-3", "abc", "1.5", True):
            with self.assertRaises(NotConfigured, msg=repr(value)):
                _parse(days=value)


class TestRequireReady(unittest.TestCase):
    def test_complete_config_is_returned(self):
        parsed = _parse()
        self.assertIs(parsed.require_ready(), parsed)

    def test_missing_url_is_reported(self):
        with self.assertRaises(NotConfigured) as raised:
            _parse(url=None).require_ready()
        self.assertEqual(raised.exception.context, {"portal_url": False, "secret": True})

    def test_missing_secret_is_reported(self):
        with self.assertRaises(NotConfigured) as raised:
            _parse(secret="short").require_ready()
        self.assertEqual(raised.exception.context, {"portal_url": True, "secret": False})

    def test_both_missing_is_reported(self):
        with self.assertRaises(NotConfigured) as raised:
            _parse(url=None, secret=None).require_ready()
        self.assertEqual(raised.exception.context, {"portal_url": False, "secret": False})


if __name__ == "__main__":
    unittest.main()
