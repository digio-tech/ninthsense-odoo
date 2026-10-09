import hashlib
import json
import re
import unittest
from pathlib import Path

from core import portal_contract
from core.errors import InvalidPayload

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"
CONTRACT_TYPES_PATH = Path(__file__).resolve().parents[1] / "contract_types.py"

HEADER_LINE_RE = re.compile(r"^# (?P<name>\S+) sha256=(?P<digest>[0-9a-f]{64})$")


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text())


def _read_sums_file() -> dict[str, str]:
    sums = {}
    for line in (SCHEMA_DIR / "SHA256SUMS").read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        digest, filename = line.split(None, 1)
        sums[filename.strip()] = digest
    return sums


def _read_header_digests() -> dict[str, str]:
    digests = {}
    for line in CONTRACT_TYPES_PATH.read_text().splitlines()[:2]:
        match = HEADER_LINE_RE.match(line)
        assert match, f"unexpected contract_types.py header line: {line!r}"
        digests[match.group("name")] = match.group("digest")
    return digests


class TestSchemaDigests(unittest.TestCase):
    def test_digests_match_sums_file_and_generated_header(self):
        sums = _read_sums_file()
        header_digests = _read_header_digests()
        for filename in ("request.schema.json", "completion.schema.json"):
            actual = hashlib.sha256((SCHEMA_DIR / filename).read_bytes()).hexdigest()
            self.assertEqual(actual, sums[filename])
            self.assertEqual(actual, header_digests[filename])


class TestPortalContract(unittest.TestCase):
    def setUp(self):
        self.validators = portal_contract.load_validators(SCHEMA_DIR)

    def test_request_valid_passes(self):
        portal_contract.validate_descriptor(self.validators, _load_fixture("request_valid.json"))

    def test_completion_valid_passes(self):
        raw = json.dumps(
            {"token": "tok-1", "payload": _load_fixture("completion_valid.json")}
        ).encode()
        token, bundle = portal_contract.parse_completion(self.validators, raw)
        self.assertEqual(token, "tok-1")
        self.assertEqual(bundle.steps[0].documents[0].document_code, "pan_card")

    def test_request_unknown_field_rejected(self):
        descriptor = _load_fixture("request_unknown_field.json")
        with self.assertRaises(InvalidPayload):
            portal_contract.validate_descriptor(self.validators, descriptor)

    def test_completion_unknown_field_rejected(self):
        raw = json.dumps(
            {"token": "tok-1", "payload": _load_fixture("completion_unknown_field.json")}
        ).encode()
        with self.assertRaises(InvalidPayload):
            portal_contract.parse_completion(self.validators, raw)

    def test_version_two_is_accepted_and_any_other_rejected(self):
        accepted = _load_fixture("completion_valid.json")
        self.assertEqual(accepted["schema_version"], "2.0")
        portal_contract.parse_completion(
            self.validators, json.dumps({"token": "tok-1", "payload": accepted}).encode()
        )
        for version in ("1.0", "2.1", "3.0", ""):
            payload = dict(accepted, schema_version=version)
            raw = json.dumps({"token": "tok-1", "payload": payload}).encode()
            with self.assertRaises(InvalidPayload, msg=version):
                portal_contract.parse_completion(self.validators, raw)

    def test_expires_at_without_timezone_rejected(self):
        descriptor = _load_fixture("request_valid.json")
        descriptor["expires_at"] = "2026-09-18T10:00:00"
        with self.assertRaises(InvalidPayload):
            portal_contract.validate_descriptor(self.validators, descriptor)
