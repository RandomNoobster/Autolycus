"""Helpers for reading request data in API routes."""
from typing import Any

from flask import request


def get_json_object() -> dict[str, Any]:
    """Return the request's JSON body as a dict.

    A missing, undecodable or non-object body (for example ``[1]`` or ``"x"``)
    becomes ``{}``, so the route's own field validation returns its normal 400
    instead of an exception reaching the route's catch-all 500 handler.
    """
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}
