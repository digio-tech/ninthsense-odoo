import hashlib
import hmac
import unittest

from core import signature
from core.errors import BadSignature
from core.limits import DEFAULT_LIMITS

SECRET = "correct-horse-battery-staple"


def _header(secret: str, timestamp: int, raw: bytes) -> str:
    signed_content = f"{timestamp}.".encode() + raw
    digest = hmac.new(secret.encode("utf-8"), signed_content, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


class TestVerify(unittest.TestCase):
    def setUp(self):
        self.raw = b'{"token":"abc","payload":{}}'
        self.now = 1_700_000_000

    def test_valid_signature_passes(self):
        header = _header(SECRET, self.now, self.raw)
        signature.verify(header, self.raw, SECRET, self.now, DEFAULT_LIMITS)

    def test_header_must_match_the_exact_pattern(self):
        malformed_headers = [
            "t=123,v1=deadbeef",
            "t=abc,v1=" + "0" * 64,
            "t=123;v1=" + "0" * 64,
            f"t=123,v1={'A' * 64}",
            "",
        ]
        for header in malformed_headers:
            with self.assertRaises(BadSignature):
                signature.verify(header, self.raw, SECRET, self.now, DEFAULT_LIMITS)

    def test_none_header_fails(self):
        with self.assertRaises(BadSignature):
            signature.verify(None, self.raw, SECRET, self.now, DEFAULT_LIMITS)

    def test_skew_within_limit_passes(self):
        skewed = self.now - DEFAULT_LIMITS.signature_skew_seconds
        header = _header(SECRET, skewed, self.raw)
        signature.verify(header, self.raw, SECRET, self.now, DEFAULT_LIMITS)

    def test_skew_one_second_over_limit_fails(self):
        skewed = self.now - DEFAULT_LIMITS.signature_skew_seconds - 1
        header = _header(SECRET, skewed, self.raw)
        with self.assertRaises(BadSignature):
            signature.verify(header, self.raw, SECRET, self.now, DEFAULT_LIMITS)

    def test_signed_content_is_timestamp_dot_raw_body(self):
        # A digest computed over the wrong bytes (a re-serialised body) must fail.
        header = _header(SECRET, self.now, self.raw + b" ")
        with self.assertRaises(BadSignature):
            signature.verify(header, self.raw, SECRET, self.now, DEFAULT_LIMITS)

    def test_wrong_secret_fails(self):
        header = _header("not-the-configured-secret", self.now, self.raw)
        with self.assertRaises(BadSignature):
            signature.verify(header, self.raw, SECRET, self.now, DEFAULT_LIMITS)

    def test_no_configured_secret_fails(self):
        header = _header(SECRET, self.now, self.raw)
        with self.assertRaises(BadSignature):
            signature.verify(header, self.raw, "", self.now, DEFAULT_LIMITS)


if __name__ == "__main__":
    unittest.main()
