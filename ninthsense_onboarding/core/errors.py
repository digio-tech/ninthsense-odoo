class NinthsenseError(Exception):
    code = "error"

    def __init__(self, message: str = "", context: dict | None = None):
        super().__init__(message)
        self.message = message
        self.context = context or {}


class InvalidToken(NinthsenseError):
    code = "invalid_token"


class BadSignature(NinthsenseError):
    code = "bad_signature"


class InvalidPayload(NinthsenseError):
    code = "invalid_payload"


class UnknownDocument(NinthsenseError):
    code = "unknown_document"


class FileTypeNotAllowed(NinthsenseError):
    code = "file_type_not_allowed"


class NotOpen(NinthsenseError):
    code = "not_open"


class NotConfigured(NinthsenseError):
    code = "not_configured"


class DescriptorInvalid(NinthsenseError):
    """The descriptor this server built fails its own schema: a fault here, not the caller's."""

    code = "descriptor_invalid"
