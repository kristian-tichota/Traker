from flask import request


class BadRequest(ValueError):
    """Anything the client sent that cannot be honoured."""


class BadPayload(BadRequest):
    """A request body that cannot be read, or that is missing a field."""


class BadValue(BadRequest):
    """A value that does not belong in the column it was bound for."""


def read_payload(*required: str) -> dict:
    """This request's JSON object, once it is one and carries required."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise BadPayload("Expected a JSON object as the request body.")

    missing = [field for field in required if data.get(field) is None]
    if missing:
        raise BadPayload("Missing required field(s): " + ", ".join(sorted(missing)))
    return data
