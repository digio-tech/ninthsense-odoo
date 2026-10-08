import datetime
import json
from dataclasses import dataclass
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from . import contract_types as ct
from .errors import InvalidPayload

ACCEPTED_BUNDLE_VERSIONS = ("2.0",)
EMITTED_DESCRIPTOR_VERSION = "2.0"

REQUEST_SCHEMA_FILE = "request.schema.json"
COMPLETION_SCHEMA_FILE = "completion.schema.json"


@dataclass(frozen=True)
class Validators:
    request: Draft202012Validator
    completion: Draft202012Validator


def _build_format_checker() -> FormatChecker:
    checker = FormatChecker()

    @checker.checks("date-time", raises=ValueError)
    def _check_date_time(value: object) -> bool:
        if not isinstance(value, str):
            return True
        parsed = datetime.datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError("date-time value has no timezone offset")
        return True

    return checker


def _read_schema(path: Path) -> dict:
    return json.loads(path.read_bytes())


def load_validators(schema_dir: Path) -> Validators:
    request_schema = _read_schema(schema_dir / REQUEST_SCHEMA_FILE)
    completion_schema = _read_schema(schema_dir / COMPLETION_SCHEMA_FILE)
    checker = _build_format_checker()
    return Validators(
        request=Draft202012Validator(request_schema, format_checker=checker),
        completion=Draft202012Validator(completion_schema, format_checker=checker),
    )


def _error_summary(error) -> dict:
    return {"path": list(error.absolute_path), "validator": error.validator}


def validate_descriptor(validators: Validators, descriptor: dict) -> None:
    errors = sorted(validators.request.iter_errors(descriptor), key=lambda e: list(e.absolute_path))
    if errors:
        raise InvalidPayload(
            "descriptor failed schema validation",
            context={"errors": [_error_summary(e) for e in errors]},
        )


def parse_completion(validators: Validators, raw: bytes) -> tuple[str, ct.CompletionPayload]:
    try:
        envelope = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise InvalidPayload("malformed json body") from exc
    if not isinstance(envelope, dict):
        raise InvalidPayload("envelope must be a json object")
    token = envelope.get("token")
    if not isinstance(token, str) or not token:
        raise InvalidPayload("missing token")
    bundle = envelope.get("payload")
    if not isinstance(bundle, dict):
        raise InvalidPayload("missing payload")
    errors = sorted(validators.completion.iter_errors(bundle), key=lambda e: list(e.absolute_path))
    if errors:
        raise InvalidPayload(
            "completion bundle failed schema validation",
            context={"errors": [_error_summary(e) for e in errors]},
        )
    if bundle.get("schema_version") not in ACCEPTED_BUNDLE_VERSIONS:
        raise InvalidPayload(
            "unsupported schema_version",
            context={"schema_version": bundle.get("schema_version")},
        )
    return token, _build_completion(bundle)


def _build_completion(bundle: dict) -> ct.CompletionPayload:
    return ct.CompletionPayload(
        schema_version=bundle["schema_version"],
        ref=bundle["ref"],
        goal_key=bundle["goal_key"],
        stage=bundle["stage"],
        catalogue_version=bundle["catalogue_version"],
        status=ct.Status(bundle["status"]),
        completed_at=bundle["completed_at"],
        steps=[_build_step(step) for step in bundle["steps"]],
    )


def _build_step(step: dict) -> ct.CompletionStep:
    return ct.CompletionStep(
        id=step["id"],
        type=step["type"],
        provider=ct.Provider(**step["provider"]),
        documents=[ct.Document(**document) for document in step["documents"]],
        missing_documents=list(step["missing_documents"]),
        result=step.get("result"),
        extractions=step.get("extractions"),
    )
