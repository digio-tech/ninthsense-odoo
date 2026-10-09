from dataclasses import dataclass


@dataclass(frozen=True)
class Limits:
    signature_skew_seconds: int = 300
    token_max_length: int = 128
    stored_value_max_length: int = 1024
    file_max_mb: int = 20
    verification_document_id_max_length: int = 256


DEFAULT_LIMITS = Limits()
