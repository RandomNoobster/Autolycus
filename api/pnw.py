"""Politics & War API access shared by the calculation routes."""
from __future__ import annotations

import os
from typing import Any

from logic.api_client import call

# Longest a request thread waits for P&W-backed work before answering 504. The
# API client can otherwise keep retrying and waiting out rate limits for minutes.
UPSTREAM_TIMEOUT_SECONDS = 60

UPSTREAM_TIMEOUT_RESPONSE = {
    "error": "Upstream timeout",
    "message": "Politics & War is responding slowly. Please try again shortly.",
    "code": "UPSTREAM_TIMEOUT",
}


async def call_pnw(query: str) -> dict[str, Any]:
    """Run a GraphQL query with the server's API key."""
    api_key = os.getenv("API_KEY")
    if not api_key:
        raise RuntimeError("API_KEY environment variable must be set")
    return await call(query, api_key=api_key)
